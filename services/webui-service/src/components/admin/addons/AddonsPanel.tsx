import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  Alert,
  Box,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';
import { useTranslation } from 'react-i18next';
import { useNavigate } from 'react-router-dom';
import {
  addonsApi,
  isSettingAddon,
  pickText,
  type AddonCategory,
  type AddonEntry,
  type AddonProfile,
} from '@/api/addons';
import { useCapabilities } from '@/contexts/CapabilitiesContext';
import { useToast } from '@/contexts/ToastContext';
import { translateApiError } from '@/utils/apiError';
import { useLayout } from '@/hooks/useLayout';
import { ActionButton } from '@/components/ui/ActionButton';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { SettingsBlock } from '@/components/admin/SettingsBlock';
import { UpdateProgressDialog } from '@/components/admin/maintenance/UpdateProgressDialog';
import { useUpdateRun } from '@/components/admin/maintenance/useUpdateRun';
import { AddonRow } from './AddonRow';
import { useAddonsRun } from './useAddonsRun';

/** Accessories first: that is the group that may end in an order and a screwdriver. */
const CATEGORY_ORDER: AddonCategory[] = ['hardware', 'software'];

/**
 * The addons table: card reader, LEDs, buttons, display, media import,
 * announcements, online metadata.
 *
 * It lists every addon, including the ones this box does not have, each with
 * what it is for, what it needs and which version it is at (#181) - so an
 * addon can be found and added without reading the documentation first. The
 * descriptions come from the backend (`component_catalog.py`); this panel owns
 * the runs.
 *
 * Adding an addon was the last setup step that still needed an SSH session and
 * the maintenance menu of `install.sh` (#180).
 *
 * Two kinds of switch sit in the same table on purpose (see `api/addons.ts`):
 *
 * * A **compose addon** is a *wish* until "apply" - one press means removing
 *   and recreating containers, and the box restarts services over it. Several
 *   of them are therefore collected into one run rather than each starting
 *   their own.
 * * A **setting addon** is written the moment it is switched. There is no run
 *   to collect, so waiting for "apply" would only be a rule with no reason
 *   behind it.
 *
 * Switching an addon off deletes nothing. Its card assignments and settings
 * stay, the backend answers calls into an absent component with a 409, and
 * switching it back on is lossless - which is why there is no warning dialog
 * about data, only about the restart.
 *
 * The gear button is a link, not a second form: it jumps to the settings
 * section the addon owns (`?section=<settings_section>`, the same deep link
 * the CommandPalette uses), rather than opening the same panel again in a
 * dialog. One value, one place to edit it - see
 * `docs/services/webui/Settings-Structure.md`.
 */
export const AddonsPanel: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const navigate = useNavigate();
  const { showError } = useToast();
  const { isMobile } = useLayout();
  const { refresh: refreshCapabilities } = useCapabilities();
  const [entries, setEntries] = useState<AddonEntry[]>([]);
  const [saved, setSaved] = useState<AddonProfile[]>([]);
  const [wanted, setWanted] = useState<AddonProfile[]>([]);
  const [unreachable, setUnreachable] = useState(false);
  const [serverBusy, setServerBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [rebootRequired, setRebootRequired] = useState(false);
  const [updateFor, setUpdateFor] = useState<AddonEntry | null>(null);
  const attached = useRef(false);

  const load = useCallback(async () => {
    try {
      const data = await addonsApi.get();
      setEntries(data.components);
      setSaved(data.profiles);
      setWanted(data.profiles);
      setUnreachable(!!data.unreachable);
      setServerBusy(data.busy);
    } catch {
      setUnreachable(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const run = useAddonsRun(() => {
    void load();
    // The backend was recreated with the new COMPOSE_PROFILES, so this is the
    // moment its capabilities answer changes - and with it the whole
    // navigation.
    void refreshCapabilities();
  });

  // Updating one addon is the same machinery as updating the whole box, with
  // one target instead of all of them - `POST /system/update` has always taken
  // a set of services.
  const updateRun = useUpdateRun(() => {
    void load();
  });

  // Whether the box needs a restart is only known once a run has answered.
  useEffect(() => {
    if (run.status?.reboot_required) setRebootRequired(true);
  }, [run.status]);

  // A run that is already going when this page opens - started in another tab,
  // or here before a reload. Attaching to it is also what clears `serverBusy`
  // again: the poll ends, and the reload behind it brings the current state.
  const attach = run.attach;
  useEffect(() => {
    if (serverBusy && !attached.current) {
      attached.current = true;
      attach();
    }
  }, [serverBusy, attach]);

  const dirty = useMemo(
    () =>
      saved.length !== wanted.length ||
      saved.some((profile) => !wanted.includes(profile)),
    [saved, wanted],
  );

  const busy = run.running || updateRun.running || serverBusy;

  const nameOf = useCallback(
    (entry: AddonEntry) =>
      pickText(entry.name, i18n.language) ??
      t(`system.component_${entry.id}` as never),
    [i18n.language, t],
  );

  /**
   * A setting addon is not collected into the run: there is nothing to
   * collect. It is written at once and shown at once - and put back when the
   * write fails, so the switch never claims something the box did not store.
   */
  const toggleSetting = async (entry: AddonEntry, on: boolean) => {
    if (!isSettingAddon(entry)) return;
    const apply = (installed: boolean) =>
      setEntries((prev) =>
        prev.map((e) =>
          e.id === entry.id
            ? { ...e, installed, running: installed, healthy: installed }
            : e,
        ),
      );
    apply(on);
    try {
      await addonsApi.setSetting(entry.install.field, on);
    } catch (err) {
      apply(!on);
      showError(translateApiError(t, i18n, err));
    }
  };

  const handleToggle = (entry: AddonEntry, on: boolean) => {
    if (isSettingAddon(entry)) {
      void toggleSetting(entry, on);
      return;
    }
    const profile = entry.profile;
    if (!profile) return;
    setWanted((prev) =>
      on ? [...prev, profile] : prev.filter((p) => p !== profile),
    );
  };

  const handleApply = () => {
    setConfirmOpen(false);
    setRebootRequired(false);
    void run.start(wanted);
  };

  const handleUpdate = () => {
    const entry = updateFor;
    setUpdateFor(null);
    if (!entry?.service || !entry.latest) return;
    void updateRun.start({ [entry.service]: entry.latest });
  };

  const turningOff = saved.filter((profile) => !wanted.includes(profile));
  const turningOn = wanted.filter((profile) => !saved.includes(profile));

  const names = (profiles: AddonProfile[]) =>
    profiles
      .map((profile) => {
        const entry = entries.find((e) => e.profile === profile);
        return entry ? nameOf(entry) : profile;
      })
      .join(', ');

  const grouped = useMemo(
    () =>
      CATEGORY_ORDER.map((category) => ({
        category,
        rows: entries.filter((entry) => entry.category === category),
      })).filter((group) => group.rows.length > 0),
    [entries],
  );

  if (loading) return null;

  // Name + actions on a phone; state and version get their own columns from
  // tablet width up (see AddonRow).
  const columnCount = isMobile ? 2 : 4;

  return (
    <SettingsBlock
      title={t('addons.catalogue_title')}
      description={t('addons.catalogue_hint')}
      help={t('system.components_help')}
    >
      {unreachable && (
        <Alert severity="info">{t('system.components_unavailable')}</Alert>
      )}

      <TableContainer sx={{ overflowX: 'auto' }}>
        <Table size="small" aria-label={t('addons.catalogue_title')}>
          <TableHead>
            <TableRow>
              <TableCell>{t('addons.column_addon')}</TableCell>
              {!isMobile && <TableCell>{t('addons.column_state')}</TableCell>}
              {!isMobile && <TableCell>{t('addons.column_version')}</TableCell>}
              <TableCell align="right">{t('addons.column_actions')}</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {grouped.map((group) => (
              <React.Fragment key={group.category}>
                {/* The one split that matters to whoever runs the box: does
                    this addon need something bought and attached, or not. */}
                <TableRow>
                  <TableCell
                    colSpan={columnCount}
                    sx={{ bgcolor: 'action.hover', py: 0.5, border: 0 }}
                  >
                    <Typography variant="overline" color="text.secondary">
                      {t(`addons.category_${group.category}` as never)}
                    </Typography>
                  </TableCell>
                </TableRow>
                {group.rows.map((entry) => (
                  <AddonRow
                    key={entry.id}
                    entry={entry}
                    checked={
                      isSettingAddon(entry)
                        ? entry.installed
                        : !!entry.profile && wanted.includes(entry.profile)
                    }
                    disabled={busy || (unreachable && !isSettingAddon(entry))}
                    compact={isMobile}
                    onSettings={
                      entry.installed && entry.settings_section
                        ? () => navigate(`/admin?section=${entry.settings_section}`)
                        : undefined
                    }
                    onUpdate={
                      entry.update_available && !unreachable
                        ? () => setUpdateFor(entry)
                        : undefined
                    }
                    onToggle={(on) => handleToggle(entry, on)}
                  />
                ))}
              </React.Fragment>
            ))}
          </TableBody>
        </Table>
      </TableContainer>

      {rebootRequired && (
        // I2C only appears as /dev/i2c-1 after a restart, so the container of
        // a just-enabled card reader or display could not be started yet.
        <Alert severity="warning">{t('system.components_reboot_required')}</Alert>
      )}

      {dirty && (
        <Typography variant="caption" color="text.secondary">
          {t('system.components_restart_hint')}
        </Typography>
      )}

      <Box display="flex" flexWrap="wrap" gap={1} alignItems="center">
        <ActionButton
          actionType="primary"
          onClick={() => setConfirmOpen(true)}
          disabled={!dirty || busy || unreachable}
          loading={busy}
        >
          {t('system.components_apply')}
        </ActionButton>
        {dirty && !busy && (
          <ActionButton actionType="secondary" onClick={() => setWanted(saved)}>
            {t('actions.cancel', { ns: 'common' })}
          </ActionButton>
        )}
      </Box>

      <ConfirmDialog
        open={confirmOpen}
        title={t('system.components_apply')}
        message={[
          turningOn.length > 0
            ? t('system.components_confirm_on', { names: names(turningOn) })
            : null,
          turningOff.length > 0
            ? t('system.components_confirm_off', { names: names(turningOff) })
            : null,
          t('system.components_confirm_restart'),
        ]
          .filter(Boolean)
          .join(' ')}
        onCancel={() => setConfirmOpen(false)}
        onConfirm={handleApply}
      />

      <ConfirmDialog
        open={updateFor !== null}
        title={t('addons.update_title')}
        message={
          updateFor
            ? t('addons.update_confirm', {
                name: nameOf(updateFor),
                version: updateFor.latest,
              })
            : ''
        }
        onCancel={() => setUpdateFor(null)}
        onConfirm={handleUpdate}
      />


      <UpdateProgressDialog
        open={run.progressOpen}
        running={run.running}
        status={run.status}
        onClose={run.closeProgress}
        title={t('system.components_progress_title')}
        successText={t('system.components_success')}
        failedText={t('system.components_failed')}
        stepPrefix="system.components_step_"
      />

      <UpdateProgressDialog
        open={updateRun.progressOpen}
        running={updateRun.running}
        status={updateRun.status}
        onClose={updateRun.closeProgress}
      />
    </SettingsBlock>
  );
};
