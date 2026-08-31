import React from 'react';
import {
  Box,
  Paper,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TableSortLabel,
  Typography,
} from '@mui/material';

/**
 * One column of the Explorer-style details view. `key` doubles as the sort key
 * handed to `onSortChange` and as the React key for the column.
 */
export interface DetailsColumn<T> {
  key: string;
  label: string;
  /** Clickable header that drives `onSortChange`. */
  sortable?: boolean;
  /** Right-align the cell (durations, dates). */
  numeric?: boolean;
  /** Fixed column width, e.g. `48` or `'30%'`. */
  width?: number | string;
  render: (item: T) => React.ReactNode;
}

interface DetailsTableProps<T> {
  items: T[];
  columns: DetailsColumn<T>[];
  sortKey: string;
  sortDir: 'asc' | 'desc';
  onSortChange: (key: string, dir: 'asc' | 'desc') => void;
  rowKey: (item: T) => React.Key;
  emptyText: string;
  /** Trailing actions cell (play, edit, move, delete …). */
  renderActions?: (item: T) => React.ReactNode;
  /** Per-row drag handlers so folder drag & drop keeps working in this view. */
  onRowDragStart?: (e: React.DragEvent, item: T) => void;
  onRowDragEnd?: () => void;
  draggingKey?: React.Key | null;
}

/**
 * Sortable column table shared by TrackList/StreamList/PodcastList for the
 * "details" view mode. Deliberately desktop-only - the callers fall back to the
 * list view below the desktop breakpoint, so this component does not try to be
 * responsive itself; it only guards against horizontal overflow.
 */
export function DetailsTable<T>({
  items,
  columns,
  sortKey,
  sortDir,
  onSortChange,
  rowKey,
  emptyText,
  renderActions,
  onRowDragStart,
  onRowDragEnd,
  draggingKey,
}: DetailsTableProps<T>) {
  const handleSort = (key: string) => {
    if (key === sortKey) onSortChange(key, sortDir === 'asc' ? 'desc' : 'asc');
    else onSortChange(key, 'asc');
  };

  if (items.length === 0) {
    return (
      <Box display="flex" justifyContent="center" py={6}>
        <Typography color="text.secondary">{emptyText}</Typography>
      </Box>
    );
  }

  return (
    <TableContainer component={Paper} variant="outlined" sx={{ overflowX: 'auto' }}>
      <Table size="small" sx={{ minWidth: 640 }}>
        <TableHead>
          <TableRow>
            {columns.map((col) => (
              <TableCell
                key={col.key}
                align={col.numeric ? 'right' : 'left'}
                sortDirection={sortKey === col.key ? sortDir : false}
                sx={{ width: col.width, whiteSpace: 'nowrap', fontWeight: 600 }}
              >
                {col.sortable ? (
                  <TableSortLabel
                    active={sortKey === col.key}
                    direction={sortKey === col.key ? sortDir : 'asc'}
                    onClick={() => handleSort(col.key)}
                  >
                    {col.label}
                  </TableSortLabel>
                ) : (
                  col.label
                )}
              </TableCell>
            ))}
            {renderActions && <TableCell padding="none" sx={{ width: 1 }} />}
          </TableRow>
        </TableHead>
        <TableBody>
          {items.map((item) => {
            const key = rowKey(item);
            return (
              <TableRow
                key={key}
                hover
                draggable={Boolean(onRowDragStart)}
                onDragStart={onRowDragStart ? (e) => onRowDragStart(e, item) : undefined}
                onDragEnd={onRowDragEnd}
                sx={{
                  opacity: draggingKey === key ? 0.4 : 1,
                  cursor: onRowDragStart ? 'grab' : 'default',
                  transition: 'opacity 0.15s',
                }}
              >
                {columns.map((col) => (
                  <TableCell
                    key={col.key}
                    align={col.numeric ? 'right' : 'left'}
                    sx={{
                      maxWidth: col.width,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {col.render(item)}
                  </TableCell>
                ))}
                {renderActions && (
                  <TableCell
                    align="right"
                    padding="none"
                    sx={{ whiteSpace: 'nowrap', pr: 1 }}
                    onClick={(e) => e.stopPropagation()}
                  >
                    <Box display="flex" justifyContent="flex-end" alignItems="center">
                      {renderActions(item)}
                    </Box>
                  </TableCell>
                )}
              </TableRow>
            );
          })}
        </TableBody>
      </Table>
    </TableContainer>
  );
}
