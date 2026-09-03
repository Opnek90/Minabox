import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';

import deAdmin from '../../../../public/locales/de/admin.json';
import deCommon from '../../../../public/locales/de/common.json';
import { ServiceVersionRow } from './ServiceVersionRow';
import { RollbackSection } from './RollbackSection';
import type { RollbackCandidate, ServiceUpdateInfo } from '@/api/system';

/**
 * What the version dependency looks like on screen (#194).
 *
 * Both halves say the same thing from opposite ends: an update that waits for
 * another service, and a step back that is refused because another service is
 * waiting on this one. Both have to *name* the other service - a chip saying
 * "not now" without saying who it is waiting for would leave the user with the
 * same question one screen further away.
 */

// The real i18n substitutes the placeholders, and that is the part under test
// here: the message is worthless if it reads "wartet auf {{service}}".
const lookup = (key: string, bundle: unknown): string | undefined => {
  const value = key
    .split('.')
    .reduce<unknown>(
      (acc, part) =>
        acc && typeof acc === 'object' ? (acc as Record<string, unknown>)[part] : undefined,
      bundle,
    );
  return typeof value === 'string' ? value : undefined;
};

vi.mock('react-i18next', () => ({
  // The namespace comes from the hook for most components and from the call
  // for the odd cross-namespace key ('actions.cancel'); both have to work,
  // because RollbackSection pulls in HelpTip, which lives in 'common'.
  useTranslation: (ns?: string) => ({
    t: (key: string, options?: Record<string, unknown>) => {
      const wanted = (options?.ns as string) ?? ns ?? 'admin';
      const template = lookup(key, wanted === 'common' ? deCommon : deAdmin);
      if (template === undefined) throw new Error(`missing locale key: ${key}`);
      return template.replace(/\{\{(\w+)\}\}/g, (_, name: string) =>
        String(options?.[name] ?? ''),
      );
    },
    i18n: { language: 'de', changeLanguage: vi.fn() },
  }),
}));

const service = (extra: Partial<ServiceUpdateInfo>): ServiceUpdateInfo => ({
  service: 'webui',
  installed: '0.5.0',
  latest: '0.6.0',
  update_available: false,
  managed: true,
  releases: [],
  ...extra,
});

describe('ServiceVersionRow - an update that waits for another service', () => {
  it('names the service it is waiting for instead of offering the version', () => {
    render(
      <ServiceVersionRow
        service={service({
          requires_unmet: [{ service: 'backend', minimum: '0.7.0', installed: '0.6.0' }],
        })}
      />,
    );

    expect(screen.getByText('wartet auf backend')).toBeInTheDocument();
    // The version must not stand there as if it could be had.
    expect(screen.queryByText('→ 0.6.0')).not.toBeInTheDocument();
  });

  it('says nothing about requirements when there is nothing to wait for', () => {
    render(<ServiceVersionRow service={service({ update_available: true })} />);

    expect(screen.getByText('→ 0.6.0')).toBeInTheDocument();
    expect(screen.queryByText(/wartet auf/)).not.toBeInTheDocument();
  });
});

describe('RollbackSection - a step back that would strand another service', () => {
  const candidate = (extra: Partial<RollbackCandidate>): RollbackCandidate => ({
    service: 'backend',
    installed: '0.7.0',
    target: '0.6.0',
    recorded_at: '2026-09-01T10:00:00+00:00',
    allowed: true,
    reason: null,
    ...extra,
  });

  it('blocks the button and names who would be left behind', async () => {
    const user = userEvent.setup();
    render(
      <RollbackSection
        candidates={[
          candidate({
            allowed: false,
            reason: 'requires_unmet',
            required_by: { service: 'media-downloader', minimum: '0.7.0' },
          }),
        ]}
        disabled={false}
        onRollback={vi.fn()}
      />,
    );

    const button = screen.getByRole('button', { name: /Zurück auf 0.6.0/ });
    expect(button).toBeDisabled();

    // A disabled button swallows its own events, so the tooltip hangs off the
    // span around it - hovering the button itself would find nothing.
    await user.hover(button.parentElement as HTMLElement);
    const tooltip = await screen.findByRole('tooltip');
    expect(tooltip).toHaveTextContent('media-downloader');
    expect(tooltip).toHaveTextContent('0.7.0');
  });

  it('leaves a step back nothing objects to alone', () => {
    render(
      <RollbackSection candidates={[candidate({})]} disabled={false} onRollback={vi.fn()} />,
    );

    expect(screen.getByRole('button', { name: /Zurück auf 0.6.0/ })).toBeEnabled();
  });
});
