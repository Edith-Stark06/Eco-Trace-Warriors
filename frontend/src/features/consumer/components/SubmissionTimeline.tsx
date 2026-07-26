import { cn } from '@/lib/utils';
import { icons } from '@/lib/icons';
import { SUBMISSION_LIFECYCLE, type SubmissionStatus } from '@/types';
import { statusLabel } from '@/features/consumer/lib/submission-display';

interface SubmissionTimelineProps {
  status: SubmissionStatus;
}

/**
 * Read-only lifecycle timeline for a submission. Renders the ordered recycling
 * stages (PENDING → … → RECYCLED) and highlights the current one; stages before
 * the current status read as complete, later stages as upcoming.
 *
 * Terminal administrative states (COMPLETED, REJECTED) fall outside the linear
 * path — the timeline shows the path and calls out the terminal state
 * separately rather than misrepresenting progress.
 */
export function SubmissionTimeline({ status }: SubmissionTimelineProps) {
  const currentIndex = SUBMISSION_LIFECYCLE.indexOf(status);
  const isRejected = status === 'REJECTED';
  const isCompleted = status === 'COMPLETED';
  const CheckIcon = icons.check;
  const CircleIcon = icons.circle;

  return (
    <div>
      <ol className="flex flex-col gap-0" aria-label="Submission lifecycle">
        {SUBMISSION_LIFECYCLE.map((stage, index) => {
          // When off-path (COMPLETED/REJECTED) treat all linear stages as done
          // except the highlight, which is handled by the terminal note below.
          const isDone = currentIndex === -1 ? isCompleted : index < currentIndex;
          const isCurrent = index === currentIndex;
          const isLast = index === SUBMISSION_LIFECYCLE.length - 1;

          return (
            <li key={stage} className="flex gap-3">
              <div className="flex flex-col items-center">
                <span
                  className={cn(
                    'flex size-7 shrink-0 items-center justify-center rounded-full border',
                    isCurrent && 'border-primary bg-primary text-primary-foreground',
                    isDone && !isCurrent && 'border-primary bg-primary/10 text-primary',
                    !isDone && !isCurrent && 'border-muted-foreground/30 text-muted-foreground',
                  )}
                  aria-hidden="true"
                >
                  {isDone && !isCurrent ? (
                    <CheckIcon className="size-4" />
                  ) : (
                    <CircleIcon className={cn('size-3', isCurrent && 'fill-current')} />
                  )}
                </span>
                {!isLast && (
                  <span
                    className={cn(
                      'w-px flex-1 grow',
                      index < currentIndex ? 'bg-primary/40' : 'bg-border',
                    )}
                    aria-hidden="true"
                  />
                )}
              </div>
              <div className={cn('pb-6', isLast && 'pb-0')}>
                <p
                  className={cn(
                    'text-sm font-medium',
                    isCurrent ? 'text-foreground' : 'text-muted-foreground',
                  )}
                >
                  {statusLabel(stage)}
                  {isCurrent && (
                    <span className="ml-2 text-xs font-normal text-primary">Current</span>
                  )}
                </p>
              </div>
            </li>
          );
        })}
      </ol>

      {(isRejected || isCompleted) && (
        <p
          className={cn(
            'mt-2 rounded-md border px-3 py-2 text-sm',
            isRejected
              ? 'border-destructive/40 bg-destructive/10 text-destructive'
              : 'border-primary/40 bg-primary/10 text-primary',
          )}
        >
          This submission is marked <strong>{statusLabel(status)}</strong>.
        </p>
      )}
    </div>
  );
}
