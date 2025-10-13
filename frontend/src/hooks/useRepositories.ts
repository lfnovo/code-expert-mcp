import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useEffect } from 'react';
import api from '@/services/api';
import type { ListRepositoriesResponse, CloneRequest, CloneResponse } from '@/types/api';

/**
 * Fetch repositories from API
 */
export async function fetchRepositories(): Promise<ListRepositoriesResponse> {
  const response = await api.get<ListRepositoriesResponse>('/api/repos');
  return response.data;
}

/**
 * Clone a repository
 */
export async function cloneRepository(request: CloneRequest): Promise<CloneResponse> {
  const response = await api.post<CloneResponse>('/api/repos/clone', request);
  return response.data;
}

/**
 * Delete a repository by URL or cache path
 */
export async function deleteRepository(identifier: string): Promise<void> {
  // Determine if identifier is a URL or cache path
  const isUrl = identifier.startsWith('http://') || identifier.startsWith('https://') || identifier.startsWith('git@');
  const param = isUrl ? 'url' : 'path';
  await api.delete(`/api/repos?${param}=${encodeURIComponent(identifier)}`);
}

/**
 * Hook for managing repository list with manual refetch only
 */
export function useRepositories() {
  const queryClient = useQueryClient();

  const {
    data,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ['repositories'],
    queryFn: fetchRepositories,
    enabled: false, // Manual refetch only
    staleTime: Infinity,
    refetchOnWindowFocus: false,
    refetchOnMount: false,
    refetchOnReconnect: false,
  });

  // Initial load on mount
  useEffect(() => {
    refetch();
  }, [refetch]);

  // Clone mutation
  const cloneMutation = useMutation({
    mutationFn: cloneRepository,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] });
      refetch();
    },
  });

  // Delete mutation
  const deleteMutation = useMutation({
    mutationFn: deleteRepository,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['repositories'] });
      refetch();
    },
  });

  return {
    repositories: data?.repositories ?? [],
    totalCached: data?.total_cached ?? 0,
    maxCachedRepos: data?.max_cached_repos ?? 0,
    cacheDir: data?.cache_dir ?? '',
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
    cloneMutation,
    deleteMutation,
  };
}
