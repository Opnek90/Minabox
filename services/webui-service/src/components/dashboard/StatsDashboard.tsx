import React, { useEffect, useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Collapse,
  Grid,
  TextField,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material';
import { alpha } from '@mui/material/styles';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useTranslation } from 'react-i18next';
import type { HeatmapItem, MinutesPerDayItem, TopPlaylistItem, TopTagItem } from '@/types/api';
import { useStatsDashboard } from '@/hooks/useStatsDashboard';
import { ActionButton } from '@/components/ui/ActionButton';
import { useLayout } from '@/hooks/useLayout';

const WEEKDAY_KEYS = [
  'weekday_0',
  'weekday_1',
  'weekday_2',
  'weekday_3',
  'weekday_4',
  'weekday_5',
  'weekday_6',
] as const;

function formatChartDate(dateStr: string, locale: string): string {
  try {
    const [year, month, day] = dateStr.split('-').map(Number);
    const date = new Date(year, month - 1, day);
    return new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit' }).format(date);
  } catch {
    return dateStr.slice(5);
  }
}

// ── Timeline Heatmap helpers ────────────────────────────────────────────────

function hourColor(minutes: number, maxMinutes: number, baseColor: string): string {
  if (minutes <= 0) return 'transparent';
  const intensity = 0.25 + (minutes / Math.max(maxMinutes, 1)) * 0.75;
  return alpha(baseColor, intensity);
}

/** Short minute label; keeps one decimal while the scale is still tiny. */
function formatMinutes(value: number, maxMinutes: number): string {
  return maxMinutes < 4 ? value.toFixed(1) : String(Math.round(value));
}

interface SelectedCell {
  weekday: number;
  hour: number;
  minutes: number;
}

interface TimelineRowProps {
  label: string;
  hours: { hour: number; minutes: number }[];
  maxMinutes: number;
  baseColor: string;
  /** Touch devices have no hover: tapping a row selects the hour under the finger. */
  selectable?: boolean;
  selectedHour?: number | null;
  onSelectHour?: (hour: number, minutes: number) => void;
}

const TimelineRow: React.FC<TimelineRowProps> = ({
  label,
  hours,
  maxMinutes,
  baseColor,
  selectable = false,
  selectedHour = null,
  onSelectHour,
}) => {
  const handleSelect = (event: React.MouseEvent<HTMLDivElement>) => {
    if (!selectable || !onSelectHour) return;
    const rect = event.currentTarget.getBoundingClientRect();
    const ratio = (event.clientX - rect.left) / rect.width;
    const hour = Math.min(23, Math.max(0, Math.floor(ratio * 24)));
    onSelectHour(hour, hours[hour]?.minutes ?? 0);
  };

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Typography
        variant="caption"
        sx={{ width: 28, flexShrink: 0, color: 'text.secondary', fontSize: '0.72rem' }}
      >
        {label}
      </Typography>
      <Box
        onClick={handleSelect}
        sx={{
          flex: 1,
          height: { xs: 26, sm: 18 },
          borderRadius: '4px',
          bgcolor: 'action.hover',
          position: 'relative',
          overflow: 'hidden',
          cursor: selectable ? 'pointer' : 'default',
        }}
      >
        {hours.map((h) => {
          const cell = (
            <Box
              sx={{
                position: 'absolute',
                top: 0,
                bottom: 0,
                left: `${(h.hour / 24) * 100}%`,
                width: `${(1 / 24) * 100}%`,
                bgcolor: hourColor(h.minutes, maxMinutes, baseColor),
                borderRight: h.minutes > 0 ? '1px solid rgba(255,255,255,0.15)' : 'none',
                ...(selectedHour === h.hour
                  ? {
                      outline: '2px solid',
                      outlineColor: 'text.primary',
                      outlineOffset: '-2px',
                      zIndex: 1,
                    }
                  : {}),
              }}
            />
          );
          // No hover on touch devices – the tap handler on the track reports the value instead.
          return selectable ? (
            <React.Fragment key={h.hour}>{cell}</React.Fragment>
          ) : (
            <Tooltip
              key={h.hour}
              title={`${h.hour}:00\u2013${h.hour + 1}:00 \u2013 ${Math.round(h.minutes)}\u202fmin`}
              placement="top"
              arrow
            >
              {cell}
            </Tooltip>
          );
        })}
        {[6, 12, 18].map((h) => (
          <Box
            key={`tick-${h}`}
            sx={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: `${(h / 24) * 100}%`,
              width: '1px',
              bgcolor: 'divider',
              opacity: 0.5,
              pointerEvents: 'none',
            }}
          />
        ))}
      </Box>
    </Box>
  );
};

const LEGEND_STEPS = [0.25, 0.5, 0.75, 1] as const;

const HeatmapLegend: React.FC<{ maxMinutes: number; baseColor: string }> = ({
  maxMinutes,
  baseColor,
}) => {
  const { t } = useTranslation('admin');

  const swatch = (color: string, outlined: boolean) => ({
    width: 24,
    height: 12,
    borderRadius: '3px',
    bgcolor: color,
    border: outlined ? '1px solid' : 'none',
    borderColor: 'divider',
  });

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: 1.5, mt: 2 }}>
      <Typography variant="caption" color="text.secondary">
        {t('stats.heatmap_legend')}
      </Typography>
      <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 0.75 }}>
        <Box sx={{ textAlign: 'center' }}>
          <Box sx={swatch('transparent', true)} />
          <Typography
            variant="caption"
            sx={{ display: 'block', fontSize: '0.65rem', color: 'text.secondary' }}
          >
            {t('stats.heatmap_legend_none')}
          </Typography>
        </Box>
        {LEGEND_STEPS.map((step, i) => (
          <Box key={step} sx={{ textAlign: 'center' }}>
            <Box sx={swatch(hourColor(step * maxMinutes, maxMinutes, baseColor), false)} />
            <Typography
              variant="caption"
              sx={{ display: 'block', fontSize: '0.65rem', color: 'text.secondary' }}
            >
              {i === LEGEND_STEPS.length - 1
                ? t('stats.minutes_short', { value: formatMinutes(step * maxMinutes, maxMinutes) })
                : formatMinutes(step * maxMinutes, maxMinutes)}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
};

// ── Main component ──────────────────────────────────────────────────────────

export const StatsDashboard: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const locale = i18n.language || 'de-DE';
  const theme = useTheme();
  const isMobile = useLayout().isMobile;
  const [showDateAxis, setShowDateAxis] = useState(false);
  const [selectedCell, setSelectedCell] = useState<SelectedCell | null>(null);
  const {
    fromDate,
    toDate,
    setFromDate,
    setToDate,
    loading,
    error,
    data,
    maxMinutes,
    heatmapMax,
    load,
  } = useStatsDashboard();

  // A new period means new numbers – drop the tapped cell instead of showing stale ones.
  useEffect(() => setSelectedCell(null), [data]);

  const heatmapColor = theme.palette.primary.main;

  return (
    <Box sx={{ py: 2 }}>
      <Typography variant="h6" gutterBottom>
        {t('stats.title')}
      </Typography>

      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          flexWrap: 'wrap',
          gap: 2,
          alignItems: { xs: 'stretch', sm: 'center' },
          mb: 3,
        }}
      >
        <TextField
          type="date"
          size="small"
          label={t('stats.from')}
          value={fromDate}
          onChange={(e) => setFromDate(e.target.value)}
          InputLabelProps={{ shrink: true }}
          sx={{ width: { xs: '100%', sm: 160 } }}
        />
        <TextField
          type="date"
          size="small"
          label={t('stats.to')}
          value={toDate}
          onChange={(e) => setToDate(e.target.value)}
          InputLabelProps={{ shrink: true }}
          sx={{ width: { xs: '100%', sm: 160 } }}
        />
        <ActionButton
          actionType="primary"
          onClick={load}
          disabled={loading}
          sx={{ width: { xs: '100%', sm: 'auto' } }}
        >
          {loading ? '\u2026' : t('stats.load')}
        </ActionButton>
      </Box>

      {error && (
        <Typography color="error" sx={{ mb: 2 }}>
          {error}
        </Typography>
      )}

      {data && (
        <Grid container spacing={3}>

          {/* ── Minutes per day ── */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="subtitle2" gutterBottom>
                  {t('stats.minutes_per_day')}
                </Typography>
                <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 0.5, height: 120, mt: 1 }}>
                  {data.minutes_per_day.map((d: MinutesPerDayItem) => (
                    <Box
                      key={d.date}
                      sx={{
                        flex: 1,
                        minWidth: 8,
                        bgcolor: 'primary.main',
                        borderRadius: '4px 4px 0 0',
                        height: `${Math.round((d.minutes / maxMinutes) * 100)}%`,
                        minHeight: d.minutes > 0 ? 4 : 0,
                      }}
                      title={`${d.date}: ${Math.round(d.minutes)} min`}
                    />
                  ))}
                </Box>

                {/* Desktop: labels always visible */}
                {!isMobile && (
                  <>
                    <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5 }}>
                      {data.minutes_per_day.map((d: MinutesPerDayItem) => (
                        <Box key={d.date} sx={{ flex: 1, minWidth: 8, textAlign: 'center', fontSize: '0.7rem' }}>
                          {formatChartDate(d.date, locale)}
                        </Box>
                      ))}
                    </Box>
                    <Box sx={{ display: 'flex', gap: 0.5, mt: 0.25, fontSize: '0.7rem', color: 'text.secondary' }}>
                      {data.minutes_per_day.map((d: MinutesPerDayItem) => (
                        <Box key={`min-${d.date}`} sx={{ flex: 1, minWidth: 8, textAlign: 'center' }}>
                          {d.minutes > 0 ? `${Math.round(d.minutes)}\u202fmin` : '\u2013'}
                        </Box>
                      ))}
                    </Box>
                  </>
                )}

                {/* Mobile: accordion date axis */}
                {isMobile && (
                  <Box sx={{ mt: 1 }}>
                    <Box
                      onClick={() => setShowDateAxis((v) => !v)}
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.5,
                        cursor: 'pointer',
                        color: 'text.secondary',
                        userSelect: 'none',
                        py: 0.75,
                      }}
                    >
                      {showDateAxis ? <ExpandLessIcon fontSize="small" /> : <ExpandMoreIcon fontSize="small" />}
                      <Typography variant="caption">
                        {showDateAxis
                          ? t('stats.hide_date_axis')
                          : t('stats.show_date_axis')}
                      </Typography>
                    </Box>

                    <Collapse in={showDateAxis}>
                      {/*
                        pt:2  = 16px gap between toggle and label row
                        pb:2.5 = 20px for rotated text to fall into (5-char @ 0.65rem @ -45deg ~= 18-20px)
                      */}
                      <Box sx={{ position: 'relative', pt: 2, pb: 2.5 }}>
                        <Box
                          sx={{
                            position: 'absolute',
                            top: 16,
                            left: 0,
                            right: 0,
                            display: 'flex',
                            gap: 0.5,
                          }}
                        >
                          {data.minutes_per_day.map((d: MinutesPerDayItem) => (
                            <Box
                              key={d.date}
                              sx={{
                                flex: 1,
                                minWidth: 8,
                                fontSize: '0.65rem',
                                transformOrigin: '0% 0%',
                                transform: 'rotate(-45deg)',
                                whiteSpace: 'nowrap',
                                color: 'text.primary',
                              }}
                            >
                              {formatChartDate(d.date, locale)}
                            </Box>
                          ))}
                        </Box>
                      </Box>
                    </Collapse>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* ── Top 3 Tags ── */}
          <Grid item xs={12} sm={6}>
            <Card>
              <CardContent>
                <Typography variant="subtitle2" gutterBottom>
                  {t('stats.top_tags')}
                </Typography>
                {data.top_tags.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    {t('stats.no_data')}
                  </Typography>
                ) : (
                  <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                    {data.top_tags.map((tag: TopTagItem) => (
                      <li key={tag.tag_id}>
                        <Typography variant="body2">
                          {tag.name || `Tag #${tag.tag_id}`}
                          {'\u2005\u2014\u2005'}
                          {t('stats.scans', { count: tag.scan_count })}
                        </Typography>
                      </li>
                    ))}
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* ── Top 3 Playlists ── */}
          <Grid item xs={12} sm={6}>
            <Card>
              <CardContent>
                <Typography variant="subtitle2" gutterBottom>
                  {t('stats.top_playlists')}
                </Typography>
                {data.top_playlists.length === 0 ? (
                  <Typography variant="body2" color="text.secondary">
                    {t('stats.no_data')}
                  </Typography>
                ) : (
                  <Box component="ul" sx={{ m: 0, pl: 2.5 }}>
                    {data.top_playlists.map((pl: TopPlaylistItem) => (
                      <li key={pl.playlist_id}>
                        <Typography variant="body2">
                          {pl.name || `Playlist #${pl.playlist_id}`}
                          {'\u2005\u2014\u2005'}
                          {t('stats.plays', { count: pl.play_count })}
                        </Typography>
                      </li>
                    ))}
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* ── Heatmap: timeline bars per weekday ── */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="subtitle2" gutterBottom>
                  {t('stats.heatmap')}
                </Typography>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.75, mt: 1 }}>
                  {[0, 1, 2, 3, 4, 5, 6].map((wd) => {
                    const cells = Array.from({ length: 24 }, (_, h) => {
                      const found = (data.heatmap as HeatmapItem[]).find(
                        (r) => r.weekday === wd && r.hour === h
                      );
                      return { hour: h, minutes: found?.minutes ?? 0 };
                    });
                    return (
                      <TimelineRow
                        key={wd}
                        label={t(`stats.${WEEKDAY_KEYS[wd]}`)}
                        hours={cells}
                        maxMinutes={heatmapMax}
                        baseColor={heatmapColor}
                        selectable={isMobile}
                        selectedHour={selectedCell?.weekday === wd ? selectedCell.hour : null}
                        onSelectHour={(hour, minutes) =>
                          setSelectedCell({ weekday: wd, hour, minutes })
                        }
                      />
                    );
                  })}
                </Box>
                <Box sx={{ display: 'flex', mt: 0.5, pl: '36px' }}>
                  {[0, 6, 12, 18].map((h, i) => (
                    <Box
                      key={h}
                      sx={{
                        flex: 1,
                        fontSize: '0.65rem',
                        color: 'text.secondary',
                        textAlign: i === 0 ? 'left' : 'center',
                      }}
                    >
                      {`${h}h`}
                    </Box>
                  ))}
                </Box>

                {isMobile && (
                  <Typography
                    variant="caption"
                    sx={{
                      display: 'block',
                      mt: 1.5,
                      minHeight: 20,
                      color: selectedCell ? 'text.primary' : 'text.secondary',
                    }}
                  >
                    {selectedCell
                      ? t('stats.heatmap_selected', { day: t(`stats.${WEEKDAY_KEYS[selectedCell.weekday]}`),
                          from: selectedCell.hour,
                          to: selectedCell.hour + 1,
                          minutes: Math.round(selectedCell.minutes) })
                      : t('stats.heatmap_tap_hint')}
                  </Typography>
                )}

                {data.heatmap.length > 0 && (
                  <HeatmapLegend maxMinutes={heatmapMax} baseColor={heatmapColor} />
                )}
              </CardContent>
            </Card>
          </Grid>

        </Grid>
      )}
    </Box>
  );
};
