import { useState } from 'react';
import { RepositoryCard } from './RepositoryCard';
import { CloneDialog } from './CloneDialog';
import { DeleteDialog } from './DeleteDialog';
import { Toast } from './Toast';
import { useRepositories } from '@/hooks/useRepositories';
import { extractErrorMessage } from '@/services/api';
import type { CloneRequest } from '@/types/api';
import type { Repository } from '@/types/repository';

interface ToastState {
  message: string;
  type: 'success' | 'error';
}

export function RepositoryList() {
  const [isCloneDialogOpen, setIsCloneDialogOpen] = useState(false);
  const [deleteRepository, setDeleteRepository] = useState<Repository | null>(null);
  const [toast, setToast] = useState<ToastState | null>(null);

  const {
    repositories,
    totalCached,
    maxCachedRepos,
    isLoading,
    isError,
    error,
    refetch,
    isFetching,
    cloneMutation,
    deleteMutation,
  } = useRepositories();

  const handleClone = async (request: CloneRequest) => {
    try {
      await cloneMutation.mutateAsync(request);
      setToast({ message: 'Repository clone started successfully', type: 'success' });
    } catch (err) {
      setToast({ message: extractErrorMessage(err), type: 'error' });
      throw err;
    }
  };

  const handleDelete = async () => {
    if (!deleteRepository) return;

    try {
      // Use cache_path as identifier if URL is null
      const identifier = deleteRepository.url || deleteRepository.cache_path;
      await deleteMutation.mutateAsync(identifier);
      setToast({ message: 'Repository deleted successfully', type: 'success' });
      setDeleteRepository(null);
    } catch (err) {
      setToast({ message: extractErrorMessage(err), type: 'error' });
    }
  };

  // Loading state
  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-current border-r-transparent align-[-0.125em] motion-reduce:animate-[spin_1.5s_linear_infinite]"></div>
          <p className="mt-2 text-sm text-gray-600">Loading repositories...</p>
        </div>
      </div>
    );
  }

  // Error state
  if (isError) {
    const errorMessage = extractErrorMessage(error);
    return (
      <div className="rounded-md bg-red-50 p-4">
        <div className="flex">
          <div className="flex-shrink-0">
            <svg
              className="h-5 w-5 text-red-400"
              viewBox="0 0 20 20"
              fill="currentColor"
            >
              <path
                fillRule="evenodd"
                d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                clipRule="evenodd"
              />
            </svg>
          </div>
          <div className="ml-3">
            <h3 className="text-sm font-medium text-red-800">
              Failed to load repositories
            </h3>
            <p className="mt-2 text-sm text-red-700">{errorMessage}</p>
            <div className="mt-4">
              <button
                onClick={() => refetch()}
                className="rounded-md bg-red-50 px-3 py-2 text-sm font-medium text-red-800 hover:bg-red-100 focus:outline-none focus:ring-2 focus:ring-red-600 focus:ring-offset-2 focus:ring-offset-red-50"
              >
                Retry
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Empty state
  if (repositories.length === 0) {
    return (
      <div className="text-center py-12">
        <svg
          className="mx-auto h-12 w-12 text-gray-400"
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M20 13V6a2 2 0 00-2-2H6a2 2 0 00-2 2v7m16 0v5a2 2 0 01-2 2H6a2 2 0 01-2-2v-5m16 0h-2.586a1 1 0 00-.707.293l-2.414 2.414a1 1 0 01-.707.293h-3.172a1 1 0 01-.707-.293l-2.414-2.414A1 1 0 006.586 13H4"
          />
        </svg>
        <h3 className="mt-2 text-sm font-medium text-gray-900">No repositories</h3>
        <p className="mt-1 text-sm text-gray-500">
          Get started by cloning your first repository.
        </p>
        <div className="mt-6">
          <button
            type="button"
            onClick={() => setIsCloneDialogOpen(true)}
            className="inline-flex items-center rounded-md border border-transparent bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            Clone Repository
          </button>
        </div>
      </div>
    );
  }

  // Success state with repositories
  return (
    <>
      <CloneDialog
        isOpen={isCloneDialogOpen}
        onClose={() => setIsCloneDialogOpen(false)}
        onSubmit={handleClone}
        isLoading={cloneMutation.isPending}
      />
      <DeleteDialog
        isOpen={deleteRepository !== null}
        repository={deleteRepository}
        onClose={() => setDeleteRepository(null)}
        onConfirm={handleDelete}
        isLoading={deleteMutation.isPending}
      />
      {toast && (
        <Toast
          message={toast.message}
          type={toast.type}
          onClose={() => setToast(null)}
        />
      )}
    <div>
      {/* Header with cache info and action buttons */}
      <div className="mb-6 flex items-center justify-between">
        <div>
          <h2 className="text-lg font-medium text-gray-900">Cached Repositories</h2>
          <p className="mt-1 text-sm text-gray-500">
            {totalCached} of {maxCachedRepos} repositories cached
          </p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={() => setIsCloneDialogOpen(true)}
            className="inline-flex items-center rounded-md border border-transparent bg-blue-600 px-4 py-2 text-sm font-medium text-white shadow-sm hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2"
          >
            <svg
              className="mr-2 h-4 w-4"
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M12 4v16m8-8H4"
              />
            </svg>
            Clone Repository
          </button>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="inline-flex items-center rounded-md border border-gray-300 bg-white px-4 py-2 text-sm font-medium text-gray-700 shadow-sm hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {isFetching ? (
              <>
                <svg
                  className="mr-2 h-4 w-4 animate-spin text-gray-700"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  ></circle>
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
                Refreshing...
              </>
            ) : (
              <>
                <svg
                  className="mr-2 h-4 w-4"
                  fill="none"
                  viewBox="0 0 24 24"
                  stroke="currentColor"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
                Refresh
              </>
            )}
          </button>
        </div>
      </div>

      {/* Repository grid */}
      <div className="grid grid-cols-1 gap-6 sm:grid-cols-2 lg:grid-cols-3">
        {repositories.map((repository) => (
          <RepositoryCard
            key={repository.cache_path}
            repository={repository}
            onDelete={setDeleteRepository}
          />
        ))}
      </div>
    </div>
    </>
  );
}
