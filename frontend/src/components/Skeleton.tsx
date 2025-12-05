import React from 'react';

interface SkeletonProps extends React.HTMLAttributes<HTMLDivElement> {
  className?: string;
}

export const Skeleton: React.FC<SkeletonProps> = ({ className, ...props }) => {
  return (
    <div
      className={`animate-pulse rounded-md bg-gray-700/50 ${className}`}
      {...props}
    />
  );
};

export const SkeletonCard: React.FC<{ className?: string }> = ({ className }) => {
  return (
    <div className={`flex flex-col gap-4 rounded-lg p-6 border border-[#314368] bg-[#101623] ${className}`}>
      <div className="flex items-center gap-2">
        <Skeleton className="h-6 w-6 rounded-full" />
        <Skeleton className="h-6 w-32" />
      </div>
      <div className="flex flex-col gap-3 mt-2">
        <div className="flex justify-between items-center">
            <Skeleton className="h-6 w-20" />
            <Skeleton className="h-6 w-16" />
        </div>
        <div className="flex justify-between items-center">
            <Skeleton className="h-6 w-24" />
            <Skeleton className="h-6 w-14" />
        </div>
        <div className="flex justify-between items-center">
            <Skeleton className="h-6 w-18" />
            <Skeleton className="h-6 w-12" />
        </div>
      </div>
    </div>
  );
};

export const SkeletonRow: React.FC<{ cols: number }> = ({ cols }) => {
    return (
        <tr className="animate-pulse">
            {Array.from({ length: cols }).map((_, i) => (
                <td key={i} className="p-4">
                    <div className="h-6 w-full bg-gray-700/50 rounded"></div>
                </td>
            ))}
        </tr>
    )
};

export default Skeleton;