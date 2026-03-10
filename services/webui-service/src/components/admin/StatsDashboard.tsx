import React from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  Grid,
  TextField,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import type { HeatmapItem, MinutesPerDayItem, TopPlaylistItem, TopTagItem } from '@/types/api';
import { useStatsDashboard } from '@/hooks/useStatsDashboard';

const WEEKDAY_KEYS = [
  'weekday_0',
  'weekday_1',
  'weekday_2',
  'weekday_3',
  'weekday_4',
  'weekday_5',
  'weekday_6',
] as const;

/** fix #59: Format a date string (YYYY-MM-DD) in a locale-aware, user-friendly way.
 * Uses Intl.DateTimeFormat with the active i18n locale so German users see DD.MM.,
 * English users see MM/DD etc. Year is omitted for brevity.
 */
function formatChartDate(dateStr: string, locale: string): string {
  try {
    // Parse as local date (avoid UTC offset shifting the day)
    const [year, month, day] = dateStr.split('-').map(Number);
    const date = new Date(year, month - 1, day);
    return new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit' }).format(date);
  } catch {
    return dateStr.slice(5); // fallback: raw MM-DD
  }
}

export const StatsDashboard: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const locale = i18n.language || 'de-DE'; // fix #59: use active locale for date formatting
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

      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, alignItems: 'center', mb: 3 }}>
        <TextField
          type="date"
          size="small"
          label={t('stats.from')}
          value={fromDate}
          onChange={(e) => setFromDate(e.target.value)}
          InputLabelProps={{ shrink: true }}
          sx={{ width: 160 }}
        />
        <TextField
          type="date"
          size="small"
          label={t('stats.to')}
          value={toDate}
          onChange={(e) => setToDate(e.target.value)}
          InputLabelProps={{ shrink: true }}
          sx={{ width: 160 }}
        />
        <Button variant="contained" onClick={load} disabled={loading}>
          {loading ? '\u2026' : t('stats.load')}
        </Button>
      </Box>

      {error && (
        <Typography color="error" sx={{ mb: 2 }}>
          {error}
        </Typography>
      )}

      {data && (
        <Grid container spacing={3}>
          {/* Minutes per day */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="subtitle2" gutterBottom>
                  {t('stats.minutes_per_day')}
                </Typography>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'flex-end',
                    gap: 0.5,
                    height: 120,
                    mt: 1,
                  }}
                >
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

                {/* fix #59: Localized date row (DD.MM. based on i18n locale) */}
                <Box sx={{ display: 'flex', gap: 0.5, mt: 0.5, fontSize: '0.7rem' }}>
                  {data.minutes_per_day.map((d: MinutesPerDayItem) => (
                    <Box key={d.date} sx={{ flex: 1, minWidth: 8, textAlign: 'center' }}>
                      {formatChartDate(d.date, locale)}
                    </Box>
                  ))}
                </Box>

                {/* fix #59: Minutes row with 'min' unit label — no hover needed, touch-accessible */}
                <Box sx={{ display: 'flex', gap: 0.5, mt: 0.25, fontSize: '0.7rem', color: 'text.secondary' }}>
                  {data.minutes_per_day.map((d: MinutesPerDayItem) => (
                    <Box key={`min-${d.date}`} sx={{ flex: 1, minWidth: 8, textAlign: 'center' }}>
                      {d.minutes > 0 ? `${Math.round(d.minutes)}\u202fmin` : '\u2013'}
                    </Box>
                  ))}
                </Box>
              </CardContent>
            </Card>
          </Grid>

          {/* Top 3 Tags */}
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
                          {tag.name || `Tag #${tag.tag_id}`} — {tag.scan_count}{' '}
                          {t('stats.top_tags').toLowerCase()}
                        </Typography>
                      </li>
                    ))}
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Top 3 Playlists */}
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
                          {pl.name || `Playlist #${pl.playlist_id}`} — {pl.play_count}{' '}
                          plays
                        </Typography>
                      </li>
                    ))}
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* Heatmap */}
          <Grid item xs={12}>
            <Card>
              <CardContent>
                <Typography variant="subtitle2" gutterBottom>
                  {t('stats.heatmap')}
                </Typography>
                <Box sx={{ overflowX: 'auto' }}>
                  <Box sx={{ display: 'flex', flexDirection: 'column', gap: 0.5, minWidth: 600 }}>
                    {[0, 1, 2, 3, 4, 5, 6].map((wd) => {
                      const row = (data.heatmap as HeatmapItem[]).filter(
                        (h) => h.weekday === wd
                      );
                      return (
                        <Box
                          key={wd}
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: 0.25,
                          }}
                        >
                          <Typography
                            variant="caption"
                            sx={{ width: 28, flexShrink: 0 }}
                          >
                            {t(`stats.${WEEKDAY_KEYS[wd]}`)}
                          </Typography>
                          <Box sx={{ display: 'flex', gap: 0.25, flex: 1 }}>
                            {row
                              .sort((a, b) => a.hour - b.hour)
                              .map((h) => (
                                <Box
                                  key={`${h.weekday}-${h.hour}`}
                                  sx={{
                                    width: 14,
                                    height: 16,
                                    bgcolor:
                                      h.minutes > 0
                                        ? `rgba(25, 118, 210, ${0.2 + (h.minutes / heatmapMax) * 0.8})`
                                        : 'action.hover',
                                    borderRadius: 1,
                                  }}
                                  title={`${h.hour}:00 – ${Math.round(h.minutes)} min`}
                                />
                              ))}
                          </Box>
                        </Box>
                      );
                    })}
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                    0h … 23h
                  </Typography>
                </Box>
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
    </Box>
  );
};
