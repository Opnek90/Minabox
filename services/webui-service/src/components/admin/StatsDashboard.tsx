import React from 'react';
import {
  Box,
  Card,
  CardContent,
  Grid,
  TextField,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
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

export const StatsDashboard: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const locale = i18n.language || 'de-DE';
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('sm'));
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

                {/* Date labels – rotated on mobile, placed clearly below bars */}
                <Box
                  sx={{
                    display: 'flex',
                    gap: 0.5,
                    pt: isMobile ? 1.5 : 0.5,   // pushes labels away from bar bottom
                    pb: isMobile ? 3 : 0,        // reserve space for rotated text height
                    overflow: 'visible',
                  }}
                >
                  {data.minutes_per_day.map((d: MinutesPerDayItem) => (
                    <Box
                      key={d.date}
                      sx={{
                        flex: 1,
                        minWidth: 8,
                        fontSize: '0.65rem',
                        textAlign: isMobile ? 'left' : 'center',
                        transformOrigin: 'top left',
                        transform: isMobile ? 'rotate(-45deg)' : 'none',
                        whiteSpace: 'nowrap',
                        overflow: 'visible',
                      }}
                    >
                      {formatChartDate(d.date, locale)}
                    </Box>
                  ))}
                </Box>

                {/* Minutes row – desktop only */}
                {!isMobile && (
                  <Box sx={{ display: 'flex', gap: 0.5, mt: 0.25, fontSize: '0.7rem', color: 'text.secondary' }}>
                    {data.minutes_per_day.map((d: MinutesPerDayItem) => (
                      <Box key={`min-${d.date}`} sx={{ flex: 1, minWidth: 8, textAlign: 'center' }}>
                        {d.minutes > 0 ? `${Math.round(d.minutes)}\u202fmin` : '\u2013'}
                      </Box>
                    ))}
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

          {/* ── Heatmap: stacked mini-heatrows ── */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="subtitle2" gutterBottom>
                  {t('stats.heatmap')}
                </Typography>

                {/* Hour axis header */}
                <Box sx={{ display: 'flex', mb: 0.5, pl: '36px' }}>
                  <Box sx={{ overflowX: 'auto', flex: 1 }}>
                    <Box sx={{ display: 'flex', gap: '2px', minWidth: 'max-content' }}>
                      {Array.from({ length: 24 }, (_, h) => (
                        <Box
                          key={h}
                          sx={{
                            width: 20,
                            textAlign: 'center',
                            fontSize: '0.6rem',
                            color: 'text.secondary',
                            flexShrink: 0,
                          }}
                        >
                          {h % 6 === 0 ? `${h}h` : ''}
                        </Box>
                      ))}
                    </Box>
                  </Box>
                </Box>

                {/* One scrollable row per weekday */}
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
                  {[0, 1, 2, 3, 4, 5, 6].map((wd) => {
                    const row = (data.heatmap as HeatmapItem[])
                      .filter((h) => h.weekday === wd)
                      .sort((a, b) => a.hour - b.hour);

                    // Fill missing hours with 0
                    const cells = Array.from({ length: 24 }, (_, h) => {
                      const found = row.find((r) => r.hour === h);
                      return found ?? { weekday: wd, hour: h, minutes: 0 };
                    });

                    return (
                      <Box key={wd} sx={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        {/* Weekday label */}
                        <Typography
                          variant="caption"
                          sx={{
                            width: 32,
                            flexShrink: 0,
                            fontSize: '0.68rem',
                            color: 'text.secondary',
                          }}
                        >
                          {t(`stats.${WEEKDAY_KEYS[wd]}`)}
                        </Typography>

                        {/* Scrollable heat cells */}
                        <Box sx={{ overflowX: 'auto', flex: 1 }}>
                          <Box sx={{ display: 'flex', gap: '2px', minWidth: 'max-content' }}>
                            {cells.map((h) => (
                              <Box
                                key={h.hour}
                                title={`${h.hour}:00 \u2013 ${Math.round(h.minutes)} min`}
                                sx={{
                                  width: 20,
                                  height: 20,
                                  flexShrink: 0,
                                  borderRadius: '3px',
                                  bgcolor:
                                    h.minutes > 0
                                      ? `rgba(25, 118, 210, ${0.15 + (h.minutes / heatmapMax) * 0.85})`
                                      : 'action.hover',
                                }}
                              />
                            ))}
                          </Box>
                        </Box>
                      </Box>
                    );
                  })}
                </Box>
              </CardContent>
            </Card>
          </Grid>

        </Grid>
      )}
    </Box>
  );
};
