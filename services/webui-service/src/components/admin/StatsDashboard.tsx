import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Collapse,
  Grid,
  TextField,
  Tooltip,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useTranslation } from 'react-i18next';
import type { HeatmapItem, MinutesPerDayItem, TopPlaylistItem, TopTagItem } from '@/types/api';
import { useStatsDashboard } from '@/hooks/useStatsDashboard';
import { ActionButton } from '@/components/ui/ActionButton';

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

/** Returns rgba color for a single hour cell based on its listening intensity */
function hourColor(minutes: number, maxMinutes: number, primaryColor: string): string {
  if (minutes <= 0) return 'transparent';
  const intensity = 0.25 + (minutes / Math.max(maxMinutes, 1)) * 0.75;
  // Parse primary color or fall back to a default purple
  return `rgba(94, 53, 177, ${intensity})`;
}

interface TimelineRowProps {
  label: string;
  hours: { hour: number; minutes: number }[];
  maxMinutes: number;
}

const TimelineRow: React.FC<TimelineRowProps> = ({ label, hours, maxMinutes }) => (
  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
    {/* Weekday label */}
    <Typography
      variant="caption"
      sx={{ width: 28, flexShrink: 0, color: 'text.secondary', fontSize: '0.72rem' }}
    >
      {label}
    </Typography>

    {/* Timeline bar */}
    <Box
      sx={{
        flex: 1,
        height: 18,
        borderRadius: '4px',
        bgcolor: 'action.hover',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {hours.map((h) => (
        <Tooltip
          key={h.hour}
          title={`${h.hour}:00\u2013${h.hour + 1}:00 \u2013 ${Math.round(h.minutes)}\u202fmin`}
          placement="top"
          arrow
        >
          <Box
            sx={{
              position: 'absolute',
              top: 0,
              bottom: 0,
              left: `${(h.hour / 24) * 100}%`,
              width: `${(1 / 24) * 100}%`,
              bgcolor: hourColor(h.minutes, maxMinutes, ''),
              // subtle border between active segments for definition
              borderRight: h.minutes > 0 ? '1px solid rgba(255,255,255,0.15)' : 'none',
            }}
          />
        </Tooltip>
      ))}

      {/* Hour tick marks at 0, 6, 12, 18 */}
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

// ── Main component ──────────────────────────────────────────────────────────

export const StatsDashboard: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const locale = i18n.language || 'de-DE';
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
  const [showDateAxis, setShowDateAxis] = useState(false);
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

  return (
    <Box sx={{ py: 2 }}>
      <Typography variant="h6" gutterBottom>
        {t('stats.title')}
      </Typography>

      {/* Date pickers + Load button */}
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

                {/* Bars */}
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
                          ? t('stats.hide_date_axis', { defaultValue: 'Datumsachse ausblenden' })
                          : t('stats.show_date_axis', { defaultValue: 'Datumsachse anzeigen' })}
                      </Typography>
                    </Box>

                    <Collapse in={showDateAxis}>
                      {/*
                        paddingTop creates a gap between toggle and labels.
                        height gives the rotated text enough room without
                        overlapping anything below.
                      */}
                      <Box sx={{ pt: 1, pb: 0, height: 48, position: 'relative' }}>
                        <Box
                          sx={{
                            position: 'absolute',
                            top: 8,           // 8px from top of container = just below toggle
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
                          {tag.name || `Tag #${tag.tag_id}`} \u2014 {tag.scan_count}{' '}
                          {t('stats.top_tags').toLowerCase()}
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
                          {pl.name || `Playlist #${pl.playlist_id}`} \u2014 {pl.play_count}{' '}
                          plays
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

                {/* Rows */}
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
                      />
                    );
                  })}
                </Box>

                {/* Hour axis: 0h, 6h, 12h, 18h, 24h */}
                <Box
                  sx={{
                    display: 'flex',
                    mt: 0.5,
                    pl: '36px', // align with bar start (label width + gap)
                  }}
                >
                  {[0, 6, 12, 18, 24].map((h) => (
                    <Box
                      key={h}
                      sx={{
                        flex: h < 24 ? 6 : 0,  // 6 hour segments between ticks
                        fontSize: '0.65rem',
                        color: 'text.secondary',
                        // last label right-aligned
                        textAlign: h === 0 ? 'left' : h === 24 ? 'right' : 'left',
                      }}
                    >
                      {`${h}h`}
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>

        </Grid>
      )}
    </Box>
  );
};
