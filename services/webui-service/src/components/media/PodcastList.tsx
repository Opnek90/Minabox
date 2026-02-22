import React, { useState } from 'react';
import {
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  List,
  ListItem,
  ListItemText,
  Tooltip,
  Typography,
} from '@mui/material';
import DeleteIcon from '@mui/icons-material/Delete';
import PlayArrowIcon from '@mui/icons-material/PlayArrow';
import PodcastsIcon from '@mui/icons-material/Podcasts';
import { useTranslation } from 'react-i18next';
import { audioApi } from '@/api/audio';
import type { Podcast } from '@/types/api';

interface PodcastListProps {
  podcasts: Podcast[];
  onDelete: (podcast: Podcast) => void;
}

export const PodcastList: React.FC<PodcastListProps> = ({ podcasts, onDelete }) => {
  const { t } = useTranslation('media');
  const [podcastToDelete, setPodcastToDelete] = useState<Podcast | null>(null);

  if (podcasts.length === 0) {
    return (
      <Box display="flex" justifyContent="center" py={6}>
        <Typography color="text.secondary">
          {t('podcasts.no_podcasts', { defaultValue: 'No podcasts yet' })}
        </Typography>
      </Box>
    );
  }

  return (
    <Box>
      <List dense>
        {podcasts.map((podcast) => (
          <ListItem
            key={podcast.id}
            secondaryAction={
              <Box>
                <Tooltip title={t('tracks.play')}>
                  <IconButton
                    size="small"
                    color="primary"
                    onClick={() => audioApi.play({ podcast_id: podcast.id })}
                  >
                    <PlayArrowIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
                <Tooltip title={t('tracks.delete')}>
                  <IconButton
                    size="small"
                    color="error"
                    onClick={() => setPodcastToDelete(podcast)}
                  >
                    <DeleteIcon fontSize="small" />
                  </IconButton>
                </Tooltip>
              </Box>
            }
          >
            <Box mr={1} color="text.secondary">
              <PodcastsIcon fontSize="small" />
            </Box>
            <ListItemText
              primary={podcast.title}
              secondary={
                podcast.last_fetched_at ? (
                  <Typography variant="caption" color="text.disabled">
                    {t('podcasts.last_fetched', {
                      defaultValue: 'Fetched',
                      date: new Date(podcast.last_fetched_at).toLocaleDateString(),
                    })}
                  </Typography>
                ) : null
              }
            />
          </ListItem>
        ))}
      </List>

      <Dialog open={!!podcastToDelete} onClose={() => setPodcastToDelete(null)}>
        <DialogTitle sx={{ fontSize: '1.25rem', fontWeight: 600 }}>
          {t('podcasts.delete', { defaultValue: 'Delete Podcast' })}
        </DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('podcasts.delete_confirm', {
              defaultValue: 'Do you want to delete "{{title}}" and all its episodes?',
              title: podcastToDelete?.title,
            })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setPodcastToDelete(null)}>
            {t('cancel', { ns: 'common' })}
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => {
              if (podcastToDelete) {
                onDelete(podcastToDelete);
                setPodcastToDelete(null);
              }
            }}
          >
            {t('delete', { ns: 'common' })}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};
