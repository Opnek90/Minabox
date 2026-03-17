import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Collapse,
  Grid,
  TextField,
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

/** Aggregates heatmap items by weekday, summing all hour-minutes */
function aggregateByWeekday(heatmap: HeatmapItem[]): { weekday: number; minutes: number }[] {
  return [0, 1, 2, 3, 4, 5, 6].map((wd) => ({
    weekday: wd,
    minutes: heatmap
      .filter((h) => h.weekday === wd)
      .reduce((sum, h) => sum + h.minutes, 0),
  }));
}

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
                    {/* Toggle row */}
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

                    {/* Collapsed date labels – mt:4 keeps them well below the toggle */}
                    <Collapse in={showDateAxis}>
                      <Box
                        sx={{
                          position: 'relative',
                          height: 52,
                          mt: 4,        // pushes label zone clearly below toggle button
                        }}
                      >
                        <Box
                          sx={{
                            position: 'absolute',
                            top: 0,
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

          {/* ── Heatmap: aggregated by weekday ── */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="subtitle2" gutterBottom>
                  {t('stats.heatmap')}
                </Typography>

                {(() => {
                  const weekdayTotals = aggregateByWeekday(data.heatmap as HeatmapItem[]);
                  const maxWd = Math.max(...weekdayTotals.map((w) => w.minutes), 1);

                  return (
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1, mt: 1 }}>
                      {weekdayTotals.map((wd) => (
                        <Box key={wd.weekday} sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                          {/* Weekday label */}
                          <Typography
                            variant="caption"
                            sx={{ width: 28, flexShrink: 0, color: 'text.secondary', fontSize: '0.72rem' }}
                          >
                            {t(`stats.${WEEKDAY_KEYS[wd.weekday]}`)}
                          </Typography>

                          {/* Bar */}
                          <Box
                            sx={{
                              flex: 1,
                              height: 20,
                              borderRadius: '4px',
                              bgcolor: wd.minutes > 0
                                ? `rgba(25, 118, 210, ${0.15 + (wd.minutes / maxWd) * 0.85})`
                                : 'action.hover',
                              position: 'relative',
                              overflow: 'hidden',
                            }}
                          >
                            <Box
                              sx={{
                                position: 'absolute',
                                left: 0,
                                top: 0,
                                bottom: 0,
                                width: `${Math.round((wd.minutes / maxWd) * 100)}%`,
                                bgcolor: 'primary.main',
                                opacity: 0.25 + (wd.minutes / maxWd) * 0.75,
                                borderRadius: '4px',
                              }}
                            />
                          </Box>

                          {/* Minutes value */}
                          <Typography
                            variant="caption"
                            sx={{ width: 48, flexShrink: 0, textAlign: 'right', color: 'text.secondary', fontSize: '0.72rem' }}
                          >
                            {wd.minutes > 0 ? `${Math.round(wd.minutes)}\u202fmin` : '\u2013'}
                          </Typography>
                        </Box>
                      ))}
                    </Box>
                  );
                })()}
              </CardContent>
            </Card>
          </Grid>

        </Grid>
      )}
    </Box>
  );
};
