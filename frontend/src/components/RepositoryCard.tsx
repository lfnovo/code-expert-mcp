import { memo } from 'react';
import type { Repository } from '@/types/repository';
import { formatCacheSize, formatLastAccess, extractRepoName } from '@/lib/utils';

interface RepositoryCardProps {
  repository: Repository;
  onDelete: (repository: Repository) => void;
}

/**
 * Get badge color based on status
 */
function getStatusColor(status: string): string {
  switch (status) {
    case 'complete':
      return 'bg-green-100 text-green-800';
    case 'pending':
    case 'cloning':
    case 'building':
      return 'bg-yellow-100 text-yellow-800';
    case 'failed':
      return 'bg-red-100 text-red-800';
    default:
      return 'bg-gray-100 text-gray-800';
  }
}

export const RepositoryCard = memo(function RepositoryCard({ repository, onDelete }: RepositoryCardProps) {
  const repoName = extractRepoName(repository.url);
  const cacheSize = formatCacheSize(repository.cache_size_mb);
  const lastAccess = formatLastAccess(repository.last_access);

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white shadow-sm hover:shadow-md transition-shadow">
      <div className="p-6">
        {/* Header: Name and Clone Status */}
        <div className="flex items-start justify-between">
          <div className="flex-1 min-w-0">
            <h3 className="text-lg font-semibold text-gray-900 truncate">
              {repoName}
            </h3>
            <p className="mt-1 text-sm text-gray-500 truncate">
              {repository.url}
            </p>
          </div>
          <div className="ml-4 flex flex-col items-end space-y-1">
            <span
              className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${getStatusColor(
                repository.clone_status.status
              )}`}
            >
              Clone: {repository.clone_status.status}
            </span>
            <span
              className={`inline-flex rounded-full px-2 py-1 text-xs font-medium ${getStatusColor(
                repository.repo_map_status.status
              )}`}
            >
              Map: {repository.repo_map_status.status}
            </span>
          </div>
        </div>

        {/* Metadata Grid */}
        <dl className="mt-4 grid grid-cols-2 gap-4 text-sm">
          <div>
            <dt className="font-medium text-gray-500">Branch</dt>
            <dd className="mt-1 text-gray-900">{repository.current_branch}</dd>
          </div>
          <div>
            <dt className="font-medium text-gray-500">Strategy</dt>
            <dd className="mt-1 text-gray-900">{repository.cache_strategy}</dd>
          </div>
          <div>
            <dt className="font-medium text-gray-500">Size</dt>
            <dd className="mt-1 text-gray-900">{cacheSize}</dd>
          </div>
          <div>
            <dt className="font-medium text-gray-500">Last Access</dt>
            <dd className="mt-1 text-gray-900">{lastAccess}</dd>
          </div>
        </dl>

        {/* Error Messages */}
        {repository.clone_status.error && (
          <div className="mt-4 rounded-md bg-red-50 p-3">
            <p className="text-sm text-red-800">
              <span className="font-medium">Clone Error:</span>{' '}
              {repository.clone_status.error}
            </p>
          </div>
        )}
        {repository.repo_map_status.error && (
          <div className="mt-4 rounded-md bg-red-50 p-3">
            <p className="text-sm text-red-800">
              <span className="font-medium">Map Error:</span>{' '}
              {repository.repo_map_status.error}
            </p>
          </div>
        )}

        {/* Delete Button */}
        <div className="mt-4 flex justify-end">
          <button
            onClick={() => onDelete(repository)}
            className="inline-flex items-center rounded-md border border-red-300 bg-white px-3 py-2 text-sm font-medium text-red-700 shadow-sm hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2"
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
                d="M19 7l-.867 12.142A2 2 0 0116.138 21H7.862a2 2 0 01-1.995-1.858L5 7m5 4v6m4-6v6m1-10V4a1 1 0 00-1-1h-4a1 1 0 00-1 1v3M4 7h16"
              />
            </svg>
            Delete
          </button>
        </div>
      </div>
    </div>
  );
});
