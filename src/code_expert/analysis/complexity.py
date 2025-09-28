import logging
import lizard
from pathlib import Path
from typing import List, Dict, Any, Optional
import os
import asyncio
import concurrent.futures

logger = logging.getLogger("code_expert.analysis.complexity")


def _run_lizard_analysis(valid_files: List[str], num_threads: int) -> List[lizard.FileInformation]:
    """
    Helper function to run lizard analysis in a separate process.
    This prevents the synchronous, multi-threaded CPU-bound task from
    blocking the main asyncio event loop of the server.
    """
    if num_threads == 1:
        logger.debug(f"Running lizard analysis on {len(valid_files)} files in single-threaded mode (stable for containers)")
    else:
        logger.debug(f"Running lizard analysis on {len(valid_files)} files with {num_threads} threads")
    # lizard.analyze_files returns an iterator, so we convert it to a list
    # to ensure the analysis is complete before returning from the process.
    # Note: threads=1 forces single-threaded mode which is more stable in containers
    return list(lizard.analyze_files(valid_files, threads=num_threads))

class CodeComplexityAnalyzer:
    def __init__(self, repo_manager, repo_map_builder):
        self.repo_manager = repo_manager
        self.repo_map_builder = repo_map_builder

    async def analyze_repo_critical_files(
        self,
        repo_path: str,
        files: Optional[List[str]] = None,
        directories: Optional[List[str]] = None,
        limit: int = 50,
        include_metrics: bool = True,
    ) -> Dict[str, Any]:
        """
        Analyze repository to identify critical files based on complexity metrics.

        Args:
            repo_path: Path/URL matching what was provided to clone_repo
            files: Optional list of specific files to analyze
            directories: Optional list of specific directories to analyze
            limit: Maximum number of files to return (default: 50)
            include_metrics: Include detailed metrics in response (default: True)

        Returns:
            dict: Response with analysis results or error information
        """
        logger.info(f"Starting analysis of critical files for repo: {repo_path}")

        # Repository Status Validation - MODIFIED TO AVOID get_repository CALL
        try:
            # Calculate cache path directly instead of using get_repository
            from ..repository.path_utils import get_cache_path

            cache_path = get_cache_path(self.repo_manager.cache_dir, repo_path)

            # Check if repository exists in the filesystem
            if not cache_path.exists():
                logger.error(f"Repository not found in cache: {repo_path}")
                return {
                    "status": "error",
                    "error": f"Repository not found in cache. Please clone it first using clone_repo with URL: {repo_path}",
                }

            # Get the absolute path as string (what we previously got from repo.root_path.resolve())
            cache_path_str = str(cache_path.resolve())

            # Check if repository is in metadata and validate clone status
            with self.repo_manager.cache._file_lock():
                metadata_dict = self.repo_manager.cache._read_metadata()
                if cache_path_str not in metadata_dict:
                    logger.error(f"Repository not found in cache metadata: {repo_path}")
                    return {
                        "status": "error",
                        "error": f"Repository not found in cache. Please clone it first using clone_repo with URL: {repo_path}",
                    }

                metadata = metadata_dict[cache_path_str]
                clone_status = metadata.clone_status
                if not clone_status or clone_status["status"] != "complete":
                    logger.info(
                        f"Repository clone is not complete: {repo_path}, status: {clone_status['status'] if clone_status else 'not_started'}"
                    )
                    if clone_status and clone_status["status"] in [
                        "cloning",
                        "copying",
                    ]:
                        return {
                            "status": "waiting",
                            "message": "Repository clone is in progress. Please try again later.",
                        }
                    else:
                        return {
                            "status": "error",
                            "error": f"Repository has not been cloned. Please clone it first using clone_repo with URL: {repo_path}",
                        }

            # Log success
            logger.debug(f"Repository validation successful for {repo_path}")

        except KeyError:
            # Repository not found in cache
            logger.error(f"Repository not found in cache: {repo_path}")
            return {
                "status": "error",
                "error": f"Repository not found. Please clone it first using clone_repo with URL: {repo_path}",
            }
        except ValueError as e:
            # Repository path is invalid
            logger.error(f"Invalid repository path: {repo_path}. Error: {str(e)}")
            return {"status": "error", "error": f"Invalid repository path: {str(e)}"}
        except Exception as e:
            # Other repository-related errors
            logger.error(
                f"Error accessing repository {repo_path}: {str(e)}", exc_info=True
            )

            # Check if this is a "clone in progress" situation
            if "clone in progress" in str(e).lower():
                return {
                    "status": "waiting",
                    "message": "Repository clone is in progress. Please try again later.",
                }

            return {"status": "error", "error": f"Repository error: {str(e)}"}

        # File Selection Strategy - MODIFIED TO USE cache_path DIRECTLY
        try:
            # Use existing RepoMapBuilder methods with the cache path
            if files or directories:
                # Use targeted file selection when specific paths are provided
                target_files = await self.repo_map_builder.gather_files_targeted(
                    str(cache_path),  # Use cache_path directly
                    files=files,
                    directories=directories,
                )
            else:
                # Fall back to full repository scan if no specific paths provided
                target_files = await self.repo_map_builder.gather_files(
                    str(cache_path)
                )  # Use cache_path directly

            # Check if we have files to analyze
            if not target_files:
                logger.info(
                    f"No matching source files found in {repo_path} with specified criteria"
                )
                return {
                    "status": "success",
                    "files": [],
                    "total_files_analyzed": 0,
                    "files_with_analysis": 0,
                    "files_without_analysis": 0,
                    "results_truncated": False,
                }

            logger.info(f"Selected {len(target_files)} files for complexity analysis")

        except Exception as e:
            logger.error(f"Error during file selection: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": f"Failed to gather target files: {str(e)}",
            }

        # Complexity Analysis Integration - MODIFIED TO USE cache_path DIRECTLY
        try:
            # Prepare result structures
            original_results = []
            files_with_analysis = 0

            # Use our cache path directly
            repo_root = Path(cache_path)  # No need for str(repo.root_path)

            # Create a list of valid file paths (string paths, not Path objects)
            valid_files = []
            for file_path in target_files:
                file_path_obj = Path(file_path)
                if file_path_obj.is_file():
                    valid_files.append(str(file_path_obj))

            # Use lizard's batch analyze_files method with an appropriate thread count
            # Number of threads can be adjusted based on system resources and file count
            num_threads = min(
                os.cpu_count() or 4, 8
            )  # Use at most 8 threads, or fewer if CPU count is lower
            
            # Get the current asyncio event loop
            loop = asyncio.get_running_loop()

            # Check if we're running in a container (Docker)
            # In containers, ProcessPoolExecutor can hang, so use ThreadPoolExecutor
            in_container = os.path.exists('/.dockerenv') or os.environ.get('CONTAINER', False)
            
            if in_container:
                logger.debug(f"Running in container, using single-threaded lizard analysis on {len(valid_files)} files")
                # Use ThreadPoolExecutor with single-threaded lizard in containers to avoid deadlocks
                with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                    file_analyses = await loop.run_in_executor(
                        pool, _run_lizard_analysis, valid_files, 1  # Force single-threaded mode in container
                    )
            else:
                logger.debug(f"Analyzing {len(valid_files)} files using {num_threads} threads via ProcessPoolExecutor")
                # Run the synchronous, multi-threaded lizard analysis in a separate process
                # to avoid blocking the asyncio event loop.
                with concurrent.futures.ProcessPoolExecutor(max_workers=1) as pool:
                    try:
                        # Add timeout to prevent hanging
                        file_analyses = await asyncio.wait_for(
                            loop.run_in_executor(
                                pool, _run_lizard_analysis, valid_files, num_threads
                            ),
                            timeout=300  # 5 minute timeout
                        )
                    except asyncio.TimeoutError:
                        logger.error(f"Lizard analysis timed out after 5 minutes for {len(valid_files)} files")
                        return {
                            "status": "error",
                            "error": "Complexity analysis timed out. Repository may be too large.",
                        }


            # NOTE: Lizard will silently skip files that it cannot process (no parser available)
            # or files that don't contain any functions. These will not appear in the returned
            # file_analyses, and there's no direct way to determine which files were skipped.
            
            # Process each file analysis
            for file_analysis in file_analyses:
                try:
                    file_path = file_analysis.filename

                    # Skip files with no functions
                    if not file_analysis.function_list:
                        continue

                    # Calculate metrics
                    total_ccn = sum(
                        f.cyclomatic_complexity for f in file_analysis.function_list
                    )
                    max_ccn = max(
                        (f.cyclomatic_complexity for f in file_analysis.function_list),
                        default=0,
                    )
                    function_count = len(file_analysis.function_list)
                    nloc = file_analysis.nloc

                    # Calculate importance score
                    score = self.calculate_importance_score(
                        function_count, total_ccn, max_ccn, nloc
                    )

                    # Convert absolute path to repository-relative path in OS-agnostic way
                    # Using os.path.relpath for cross-platform compatibility
                    relative_path = os.path.relpath(file_path, str(repo_root))

                    # Create result entry
                    result_entry = {
                        "path": relative_path,
                        "importance_score": round(score, 2),
                    }

                    # Add metrics if requested
                    if include_metrics:
                        result_entry["metrics"] = {
                            "total_ccn": total_ccn,
                            "max_ccn": max_ccn,
                            "function_count": function_count,
                            "nloc": nloc,
                        }

                    original_results.append(result_entry)
                    files_with_analysis += 1

                except Exception as e:
                    logger.warning(
                        f"Error processing analysis for file {file_path}: {str(e)}"
                    )
                    continue

            # Calculate files without analysis
            files_without_analysis = len(valid_files) - files_with_analysis

            # Sort results by importance score in descending order
            original_results.sort(key=lambda x: x["importance_score"], reverse=True)

            # Determine if results were truncated and apply limit
            results_truncated = limit > 0 and len(original_results) > limit
            limited_results = (
                original_results[:limit] if limit > 0 else original_results
            )

            # Return formatted response with new fields
            return {
                "status": "success",
                "files": limited_results,
                "total_files_analyzed": len(valid_files),
                "files_with_analysis": files_with_analysis,
                "files_without_analysis": files_without_analysis,
                "results_truncated": results_truncated,
            }

        except Exception as e:
            logger.error(f"Error during complexity analysis: {str(e)}", exc_info=True)
            return {
                "status": "error",
                "error": f"Failed to analyze file complexity: {str(e)}",
            }

    def calculate_importance_score(self, function_count, total_ccn, max_ccn, nloc):
        """Calculate importance score using the weighted formula."""
        return (
            (2.0 * function_count) + (1.5 * total_ccn) + (1.2 * max_ccn) + (0.05 * nloc)
        )

    async def analyze_and_cache_critical_files(self, cache_path: str):
        """
        Analyze critical files in background and cache the results.
        This runs after repository clone/copy is complete.
        
        Args:
            cache_path: The absolute path to the cached repository
        """
        from datetime import datetime
        import git
        
        logger.info(f"Starting background critical files analysis for {cache_path}")
        
        try:
            # Check if analysis is already running to prevent duplicates
            with self.repo_manager.cache._file_lock():
                metadata = self.repo_manager.cache._read_metadata()
                if cache_path in metadata:
                    existing_analysis = metadata[cache_path].critical_files_analysis
                    if existing_analysis and existing_analysis.get("status") == "analyzing":
                        logger.warning(f"Analysis already in progress for {cache_path}, skipping duplicate")
                        return
            
            # Update status to analyzing
            await self.repo_manager.cache.update_critical_files_analysis(
                cache_path,
                {
                    "status": "analyzing",
                    "started_at": datetime.now().isoformat(),
                }
            )
            
            # Get current git commit hash if it's a git repo
            commit_hash = None
            try:
                repo = git.Repo(cache_path)
                commit_hash = str(repo.head.commit.hexsha)
            except (git.InvalidGitRepositoryError, git.NoSuchPathError):
                # Not a git repo (local folder), use modification time as cache key
                import os
                import hashlib
                # Create a simple hash of directory structure and modification times
                dir_hash = hashlib.md5()
                for root, dirs, files in os.walk(cache_path):
                    for f in sorted(files):
                        file_path = os.path.join(root, f)
                        try:
                            stat = os.stat(file_path)
                            dir_hash.update(f"{f}:{stat.st_mtime}:{stat.st_size}".encode())
                        except:
                            pass
                commit_hash = dir_hash.hexdigest()[:12]
            
            # Run the full analysis (no limit, no specific files/directories)
            # We need to provide the original repo path that would match the metadata
            # The analyze_repo_critical_files expects the original path
            # Get the original URL from metadata
            original_path = None
            with self.repo_manager.cache._file_lock():
                metadata = self.repo_manager.cache._read_metadata()
                if cache_path in metadata:
                    original_path = metadata[cache_path].url
            
            if not original_path:
                # Fall back to using cache path directly
                original_path = cache_path
                
            analysis_result = await self.analyze_repo_critical_files(
                repo_path=original_path,  # Use original path for proper lookup
                files=None,
                directories=None,
                limit=0,  # No limit - get all files
                include_metrics=True,
            )
            
            if analysis_result.get("status") == "success":
                # Cache the successful results
                cache_data = {
                    "status": "complete",
                    "analyzed_at": datetime.now().isoformat(),
                    "commit_hash": commit_hash,
                    "parameters": {
                        "files": None,
                        "directories": None,
                    },
                    "results": {
                        "files": analysis_result.get("files", []),
                        "total_files_analyzed": analysis_result.get("total_files_analyzed", 0),
                        "files_with_analysis": analysis_result.get("files_with_analysis", 0),
                        "files_without_analysis": analysis_result.get("files_without_analysis", 0),
                    }
                }
                
                await self.repo_manager.cache.update_critical_files_analysis(
                    cache_path,
                    cache_data
                )
                
                logger.info(f"Successfully cached critical files analysis for {cache_path}")
                logger.info(f"Analyzed {len(analysis_result.get('files', []))} critical files")
            else:
                # Mark as failed
                await self.repo_manager.cache.update_critical_files_analysis(
                    cache_path,
                    {
                        "status": "failed",
                        "completed_at": datetime.now().isoformat(),
                        "error": analysis_result.get("error", "Unknown error during analysis"),
                    }
                )
                logger.error(f"Failed to analyze critical files: {analysis_result.get('error')}")
                
        except Exception as e:
            logger.error(f"Error during background critical files analysis: {str(e)}", exc_info=True)
            # Update status to failed
            await self.repo_manager.cache.update_critical_files_analysis(
                cache_path,
                {
                    "status": "failed",
                    "completed_at": datetime.now().isoformat(),
                    "error": str(e),
                }
            )
