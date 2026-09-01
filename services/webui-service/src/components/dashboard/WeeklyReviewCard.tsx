import React, { useState } from 'react';
import {
  Box,
  Card,
  CardContent,
  Collapse,
  IconButton,
  Typography,
} from '@mui/material';
import ChevronLeftIcon from '@mui/icons-material/ChevronLeft';
import ChevronRightIcon from '@mui/icons-material/ChevronRight';
import ArrowUpwardIcon from '@mui/icons-material/ArrowUpward';
import ArrowDownwardIcon from '@mui/icons-material/ArrowDownward';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import { useTranslation } from 'react-i18next';
import { HelpTip } from '@/components/ui/HelpTip';
import { useWeeklyReview } from '@/hooks/useWeeklyReview';

const WEEKDAY_KEYS = [
  'weekday_0',
  'weekday_1',
  'weekday_2',
  'weekday_3',
  'weekday_4',
  'weekday_5',
  'weekday_6',
] as const;

function formatDay(dateStr: string, locale: string): string {
  try {
    const [y, m, d] = dateStr.split('-').map(Number);
    return new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit' }).format(
      new Date(y, m - 1, d)
    );
  } catch {
    return dateStr;
  }
}

export const WeeklyReviewCard: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const locale = i18n.language || 'de-DE';
  const { weekOffset, data, loading, error, goPrev, goNext } = useWeeklyReview(1);
  const [showNeverPlayed, setShowNeverPlayed] = useState(false);

  /** Whole minutes as "2 Std. 5 Min." / "35 Min." */
  const hm = (mins: number): string => {
    const m = Math.max(0, Math.round(mins));
    if (m < 60) return t('stats.weekly.minutes_only', { m });
    return t('stats.weekly.hours_minutes', { h: Math.floor(m / 60), m: m % 60 });
  };

  const maxWeekday = data
    ? Math.max(...data.minutes_per_weekday, 1)
    : 1;

  const delta = data?.delta_minutes ?? 0;
  const deltaPct =
    data && data.prev_total_minutes > 0
      ? Math.round((delta / data.prev_total_minutes) * 100)
      : null;

  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: 1,
          }}
        >
          <Typography variant="h6">{t('stats.weekly.title')}</Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <IconButton
              size="small"
              onClick={goPrev}
              aria-label={t('stats.weekly.prev_week')}
            >
              <ChevronLeftIcon />
            </IconButton>
            <IconButton
              size="small"
              onClick={goNext}
              disabled={weekOffset === 0}
              aria-label={t('stats.weekly.next_week')}
            >
              <ChevronRightIcon />
            </IconButton>
          </Box>
        </Box>

        {data && (
          <Typography variant="caption" color="text.secondary">
            {formatDay(data.week_start, locale)} {'–'} {formatDay(data.week_end, locale)}
          </Typography>
        )}

        {error && (
          <Typography color="error" sx={{ mt: 2 }}>
            {error}
          </Typography>
        )}

        {data && !error && (
          <Box sx={{ mt: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
            {/* ── Total + delta ── */}
            <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1.5, flexWrap: 'wrap' }}>
              <Typography variant="h4" component="span">
                {hm(data.total_minutes)}
              </Typography>
              {delta !== 0 && (
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.25,
                    color: delta > 0 ? 'success.main' : 'text.secondary',
                  }}
                >
                  {delta > 0 ? (
                    <ArrowUpwardIcon fontSize="small" />
                  ) : (
                    <ArrowDownwardIcon fontSize="small" />
                  )}
                  <Typography variant="body2">
                    {hm(Math.abs(delta))}
                    {deltaPct !== null && ` (${deltaPct > 0 ? '+' : ''}${deltaPct}\u202f%)`}
                  </Typography>
                </Box>
              )}
              <Typography variant="body2" color="text.secondary">
                {delta === 0
                  ? t('stats.weekly.same_as_prev')
                  : t('stats.weekly.vs_prev', { value: hm(data.prev_total_minutes) })}
              </Typography>
            </Box>

            {/* ── Weekday bars ── */}
            <Box>
              <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 0.75, height: 72 }}>
                {data.minutes_per_weekday.map((m, wd) => (
                  <Box
                    key={wd}
                    sx={{
                      flex: 1,
                      bgcolor: 'primary.main',
                      borderRadius: '4px 4px 0 0',
                      height: `${Math.round((m / maxWeekday) * 100)}%`,
                      minHeight: m > 0 ? 4 : 0,
                    }}
                    title={`${t(`stats.${WEEKDAY_KEYS[wd]}`)}: ${hm(m)}`}
                  />
                ))}
              </Box>
              <Box sx={{ display: 'flex', gap: 0.75, mt: 0.5 }}>
                {WEEKDAY_KEYS.map((key, wd) => (
                  <Box
                    key={wd}
                    sx={{ flex: 1, textAlign: 'center', fontSize: '0.7rem', color: 'text.secondary' }}
                  >
                    {t(`stats.${key}`)}
                  </Box>
                ))}
              </Box>
            </Box>

            {/* ── Daily limit line ── */}
            <Typography variant="body2" color="text.secondary">
              {data.daily_limit_enabled
                ? t('stats.weekly.limit_line', {
                    limit: data.daily_limit_minutes,
                    avg: Math.round(data.average_minutes_per_day),
                  })
                : t('stats.weekly.no_limit_line', {
                    avg: Math.round(data.average_minutes_per_day),
                  })}
            </Typography>

            {/* ── Most played ── */}
            <Typography variant="body2">
              <strong>{t('stats.weekly.most_played')}:</strong>{' '}
              {data.most_played
                ? `${data.most_played.name || `Tag #${data.most_played.tag_id}`} — ${t(
                    'stats.plays',
                    { count: data.most_played.play_count }
                  )}`
                : t('stats.no_data')}
            </Typography>

            {/* ── Never played ── */}
            <Box>
              <Box
                onClick={() =>
                  data.never_played_total > 0 && setShowNeverPlayed((v) => !v)
                }
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.5,
                  cursor: data.never_played_total > 0 ? 'pointer' : 'default',
                }}
              >
                {data.never_played_total > 0 &&
                  (showNeverPlayed ? (
                    <ExpandLessIcon fontSize="small" />
                  ) : (
                    <ExpandMoreIcon fontSize="small" />
                  ))}
                <Typography variant="body2">
                  <strong>{t('stats.weekly.never_played')}:</strong>{' '}
                  {t('stats.weekly.never_played_count', { count: data.never_played_total })}
                </Typography>
                <HelpTip
                  title={t('stats.weekly.never_played_help')}
                  label={t('stats.weekly.never_played')}
                />
              </Box>
              <Collapse in={showNeverPlayed}>
                <Box component="ul" sx={{ mt: 0.5, mb: 0, pl: 2.5 }}>
                  {data.never_played.map((n) => (
                    <li key={n.tag_id}>
                      <Typography variant="body2">
                        {n.name || `Tag #${n.tag_id}`}
                        {n.created_at &&
                          ` — ${t('stats.weekly.since', {
                            date: formatDay(n.created_at, locale),
                          })}`}
                      </Typography>
                    </li>
                  ))}
                  {data.never_played_total > data.never_played.length && (
                    <li>
                      <Typography variant="body2" color="text.secondary">
                        {t('stats.weekly.and_more', {
                          count: data.never_played_total - data.never_played.length,
                        })}
                      </Typography>
                    </li>
                  )}
                </Box>
              </Collapse>
            </Box>

            {data.total_minutes === 0 && (
              <Typography variant="body2" color="text.secondary">
                {t('stats.weekly.empty')}
              </Typography>
            )}
          </Box>
        )}

        {loading && !data && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
            {'…'}
          </Typography>
        )}
      </CardContent>
    </Card>
  );
};
