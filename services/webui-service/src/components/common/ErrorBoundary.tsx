import React, { Component } from 'react';
import { Box, Button, Stack, Typography } from '@mui/material';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import BugReportIcon from '@mui/icons-material/BugReport';
import { useTranslation } from 'react-i18next';
import { DebugExportDialog } from '@/components/admin/DebugExportDialog';
import { recordClientError } from '@/utils/debugRingBuffer';

interface Props {
  children: React.ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  exportOpen: boolean;
}

interface FallbackProps {
  message?: string;
  exportOpen: boolean;
  onRetry: () => void;
  onOpenExport: () => void;
  onCloseExport: () => void;
}

/**
 * The visible half of the boundary.
 *
 * Split off from the class because a class cannot call `useTranslation`, and
 * the one screen an English-speaking user is most likely to hit should not be
 * the one screen that is German only.
 */
const ErrorFallback: React.FC<FallbackProps> = ({
  message,
  exportOpen,
  onRetry,
  onOpenExport,
  onCloseExport,
}) => {
  const { t } = useTranslation('common');

  return (
    <Box
      display="flex"
      flexDirection="column"
      alignItems="center"
      justifyContent="center"
      gap={2}
      sx={{ minHeight: '50vh', p: 4 }}
    >
      <ErrorOutlineIcon sx={{ fontSize: 64, color: 'error.main' }} />
      <Typography variant="h5" color="error">
        {t('error_boundary.title')}
      </Typography>
      <Typography variant="body2" color="text.secondary" textAlign="center">
        {message ?? t('error_boundary.unknown')}
      </Typography>
      <Stack direction="row" spacing={1} flexWrap="wrap" justifyContent="center" useFlexGap>
        <Button variant="contained" onClick={onRetry}>
          {t('error_boundary.retry')}
        </Button>
        {/* Most valuable right here: the ring buffer still holds the crash, and
            nobody navigates to the settings from this screen anyway. */}
        <Button variant="outlined" startIcon={<BugReportIcon />} onClick={onOpenExport}>
          {t('debug_export')}
        </Button>
      </Stack>
      <DebugExportDialog open={exportOpen} onClose={onCloseExport} />
    </Box>
  );
};

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null, exportOpen: false };
  }

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: React.ErrorInfo) {
    console.error('[WebUI] Uncaught error:', error, info);
    // A render crash never reaches window.onerror, so it has to be recorded
    // here — otherwise the debug export is missing the very error the user is
    // looking at.
    recordClientError({
      kind: 'error',
      message: error.message,
      stack: `${error.stack ?? ''}\n${info.componentStack ?? ''}`,
    });
  }

  handleReset = () => {
    this.setState({ hasError: false, error: null });
  };

  render() {
    if (this.state.hasError) {
      return (
        <ErrorFallback
          message={this.state.error?.message}
          exportOpen={this.state.exportOpen}
          onRetry={this.handleReset}
          onOpenExport={() => this.setState({ exportOpen: true })}
          onCloseExport={() => this.setState({ exportOpen: false })}
        />
      );
    }

    return this.props.children;
  }
}
