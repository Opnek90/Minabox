import React, { useState } from 'react';
import { useTranslation } from 'react-i18next';
import { useToast } from '@/contexts/ToastContext';
import { systemApi } from '@/api/system';
import { ActionButton } from '@/components/ui/ActionButton';
import { ConfirmDialog } from '@/components/common/ConfirmDialog';
import { translateApiError } from '@/utils/apiError';

/** `docker system prune` auf dem Host - raeumt alte Images weg, behaelt getaggte. */
export const CleanupButton: React.FC = () => {
  const { t, i18n } = useTranslation('admin');
  const { showSuccess, showError } = useToast();
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [pending, setPending] = useState(false);

  const handleCleanup = async () => {
    setConfirmOpen(false);
    setPending(true);
    try {
      await systemApi.dockerPrune();
      showSuccess(t('system.cleanup_success'));
    } catch (err) {
      showError(translateApiError(t, i18n, err));
    } finally {
      setPending(false);
    }
  };

  return (
    <>
      <ActionButton
        actionType="destructive"
        onClick={() => setConfirmOpen(true)}
        disabled={pending}
        loading={pending}
      >
        {t('system.cleanup')}
      </ActionButton>

      <ConfirmDialog
        open={confirmOpen}
        title={t('system.cleanup')}
        message={t('system.cleanup_confirm')}
        destructive
        onCancel={() => setConfirmOpen(false)}
        onConfirm={handleCleanup}
      />
    </>
  );
};
