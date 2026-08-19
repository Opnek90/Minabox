import React, { Component } from 'react';
import { Box, Button, Stack, Typography } from '@mui/material';
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';
import BugReportIcon from '@mui/icons-material/BugReport';
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
            Ein Fehler ist aufgetreten
          </Typography>
          <Typography variant="body2" color="text.secondary" textAlign="center">
            {this.state.error?.message ?? 'Unbekannter Fehler'}
          </Typography>
          <Stack direction="row" spacing={1} flexWrap="wrap" justifyContent="center" useFlexGap>
            <Button variant="contained" onClick={this.handleReset}>
              Erneut versuchen
            </Button>
            {/* Hier ist der Export am wertvollsten: der Ringpuffer enthaelt den
                Absturz gerade frisch, und in die Einstellungen navigiert von
                diesem Bildschirm aus ohnehin niemand mehr. */}
            <Button
              variant="outlined"
              startIcon={<BugReportIcon />}
              onClick={() => this.setState({ exportOpen: true })}
            >
              Diagnose-Paket erstellen
            </Button>
          </Stack>
          <DebugExportDialog
            open={this.state.exportOpen}
            onClose={() => this.setState({ exportOpen: false })}
          />
        </Box>
      );
    }

    return this.props.children;
  }
}
