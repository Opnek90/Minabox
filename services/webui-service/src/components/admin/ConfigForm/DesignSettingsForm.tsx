import React, { useEffect, useRef, useState } from 'react';
import {
  Box,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  ToggleButton,
  ToggleButtonGroup,
  Tooltip,
  Typography,
} from '@mui/material';
import UploadIcon from '@mui/icons-material/Upload';
import DeleteIcon from '@mui/icons-material/Delete';
import DarkModeIcon from '@mui/icons-material/DarkMode';
import LightModeIcon from '@mui/icons-material/LightMode';
import FormatSizeIcon from '@mui/icons-material/FormatSize';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { configApi } from '@/api/config';
import { useThemeContext, COLOR_PRESETS, type ColorPresetKey } from '@/contexts/ThemeContext';
import { ActionButton } from '@/components/ui/ActionButton';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { LANGUAGE_STORAGE_KEY, SUPPORTED_LANGUAGES, resolveSupportedLanguage } from '@/i18n/languages';

const COLOR_PRESET_LABELS: Record<ColorPresetKey, string> = {
  orange: 'Orange',
  blue: 'Blue',
  green: 'Green',
  purple: 'Purple',
  red: 'Red',
  pink: 'Pink',
  indigo: 'Indigo',
  teal: 'Petrol',
};

export const DesignSettingsForm: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const { mode, colorPreset, fontScale, toggleMode, setColorPreset, setFontScale } = useThemeContext();
  const [logoUrl, setLogoUrl] = useState<string | null>(null);
  const [logoUploading, setLogoUploading] = useState(false);
  const logoInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    fetch('/static/logo.png', { method: 'HEAD' })
      .then((r) => { if (r.ok) setLogoUrl('/static/logo.png?t=' + Date.now()); })
      .catch(() => null);
  }, []);

  const handleLogoUpload = async (file: File) => {
    setLogoUploading(true);
    try {
      await configApi.uploadLogo(file);
      setLogoUrl('/static/logo.png?t=' + Date.now());
      showSuccess(t('general.logo_upload_success'));
    } catch {
      showError(t('general.logo_upload_error'));
    } finally {
      setLogoUploading(false);
    }
  };

  const handleLogoDelete = async () => {
    try {
      await configApi.deleteLogo();
      setLogoUrl(null);
      showSuccess(t('general.logo_delete_success'));
    } catch {
      showError(t('general.logo_delete_error'));
    }
  };

  const handleLanguageChange = (lng: string) => {
    void i18n.changeLanguage(lng);
    localStorage.setItem(LANGUAGE_STORAGE_KEY, lng);
  };

  return (
    <Box>
      <SettingsBlock title={t('general.logo')}>
        <Box display="flex" alignItems="center" gap={2} flexWrap="wrap">
          {logoUrl && (
            <Box
              component="img"
              src={logoUrl}
              alt="Logo"
              sx={{
                height: 48,
                maxWidth: 160,
                objectFit: 'contain',
                borderRadius: 1,
                border: '1px solid',
                borderColor: 'divider',
              }}
            />
          )}
          <input
            ref={logoInputRef}
            type="file"
            accept="image/*"
            style={{ display: 'none' }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) handleLogoUpload(f); }}
          />
          <ActionButton
            actionType="secondary"
            size="small"
            startIcon={<UploadIcon />}
            onClick={() => logoInputRef.current?.click()}
            disabled={logoUploading}
          >
            {t('general.logo_upload')}
          </ActionButton>
          {logoUrl && (
            <ActionButton
              actionType="secondary"
              size="small"
              color="error"
              startIcon={<DeleteIcon />}
              onClick={handleLogoDelete}
            >
              {t('general.logo_delete')}
            </ActionButton>
          )}
        </Box>
      </SettingsBlock>

      <SettingsBlock title={t('general.language')}>
      <FormControl fullWidth size="small">
        <InputLabel>{t('general.language')}</InputLabel>
        <Select
          value={resolveSupportedLanguage(i18n.language)}
          label={t('general.language')}
          onChange={(e) => handleLanguageChange(e.target.value)}
        >
          {SUPPORTED_LANGUAGES.map((l) => (
            <MenuItem key={l.code} value={l.code}>{l.nativeName}</MenuItem>
          ))}
        </Select>
      </FormControl>
      </SettingsBlock>

      <SettingsBlock title={t('general.appearance')}>
      <Box display="flex" alignItems="center" justifyContent="space-between">
        <Typography variant="body2">{t('general.color_mode')}</Typography>
        <ToggleButtonGroup
          value={mode}
          exclusive
          onChange={(_, v) => { if (v) toggleMode(); }}
          size="small"
        >
          <ToggleButton value="light">
            <LightModeIcon fontSize="small" sx={{ mr: 0.5 }} />
            {t('general.theme_light')}
          </ToggleButton>
          <ToggleButton value="dark">
            <DarkModeIcon fontSize="small" sx={{ mr: 0.5 }} />
            {t('general.theme_dark')}
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      {/* Font size sits with light/dark, because both concern the same thing:
          how the interface looks, not what it does. */}
      <Box display="flex" alignItems="center" justifyContent="space-between" gap={2}>
        <Typography variant="body2">{t('general.font_size')}</Typography>
        <ToggleButtonGroup
          value={fontScale}
          exclusive
          onChange={(_, v) => { if (v) setFontScale(v); }}
          size="small"
        >
          <ToggleButton value="standard">
            <FormatSizeIcon fontSize="small" sx={{ mr: 0.5, fontSize: 16 }} />
            {t('general.font_size_standard')}
          </ToggleButton>
          <ToggleButton value="large">
            <FormatSizeIcon fontSize="small" sx={{ mr: 0.5 }} />
            {t('general.font_size_large')}
          </ToggleButton>
        </ToggleButtonGroup>
      </Box>

      <Box>
        <Typography variant="body2" gutterBottom>{t('general.accent_color')}</Typography>
        <Box display="flex" gap={1.5} flexWrap="wrap">
          {(Object.keys(COLOR_PRESETS) as ColorPresetKey[]).map((key) => (
            <Tooltip key={key} title={COLOR_PRESET_LABELS[key]}>
              <Box
                onClick={() => setColorPreset(key)}
                sx={{
                  width: 32,
                  height: 32,
                  borderRadius: '50%',
                  bgcolor: COLOR_PRESETS[key].main,
                  cursor: 'pointer',
                  border: colorPreset === key ? '3px solid white' : '3px solid transparent',
                  boxShadow:
                    colorPreset === key
                      ? `0 0 0 2px ${COLOR_PRESETS[key].main}`
                      : '0 1px 3px rgba(0,0,0,0.3)',
                  transition: 'transform 0.15s',
                  '&:hover': { transform: 'scale(1.15)' },
                }}
              />
            </Tooltip>
          ))}
        </Box>
      </Box>
      </SettingsBlock>
    </Box>
  );
};
