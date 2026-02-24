import React, { useRef } from 'react';
import { Box, Button, IconButton } from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import UploadIcon from '@mui/icons-material/Upload';
import { useTranslation } from 'react-i18next';

export interface CoverUploadFieldProps {
  /** Current cover URL (from entity or preview). */
  displayUrl: string | null;
  /** Pending file (not yet saved). */
  coverFile: File | null;
  onFileSelect: (file: File | null) => void;
  onRemove?: () => void;
  label?: string;
  disabled?: boolean;
  accept?: string;
}

export const CoverUploadField: React.FC<CoverUploadFieldProps> = ({
  displayUrl,
  coverFile,
  onFileSelect,
  onRemove,
  label,
  disabled = false,
  accept = 'image/*',
}) => {
  const { t } = useTranslation('media');
  const inputRef = useRef<HTMLInputElement>(null);
  const buttonLabel = label ?? t('playlists.upload_cover');
  const hasCover = !!displayUrl || !!coverFile;

  return (
    <Box display="flex" alignItems="center" gap={2} flexWrap="wrap">
      {displayUrl && (
        <Box
          component="img"
          src={displayUrl}
          alt=""
          sx={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 1 }}
        />
      )}
      <Box display="flex" alignItems="center" gap={1}>
        <Button
          variant="outlined"
          size="small"
          startIcon={<UploadIcon />}
          onClick={() => inputRef.current?.click()}
          disabled={disabled}
        >
          {coverFile ? coverFile.name : buttonLabel}
        </Button>
        {hasCover && onRemove && (
          <IconButton
            size="small"
            color="error"
            onClick={onRemove}
            disabled={disabled}
            title={t('playlists.clear_cover')}
          >
            <DeleteIcon fontSize="small" />
          </IconButton>
        )}
      </Box>
      <input
        ref={inputRef}
        type="file"
        accept={accept}
        style={{ display: 'none' }}
        onChange={(e) => {
          const file = e.target.files?.[0];
          if (file) onFileSelect(file);
          e.target.value = '';
        }}
      />
    </Box>
  );
};
