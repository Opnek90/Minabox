import { useCallback, useEffect, useRef, useState } from 'react';

/**
 * Recording a short message with the browser microphone.
 *
 * Two things about this are not obvious and decide most of the code below.
 *
 * **The browser only hands out the microphone in a secure context.** Over
 * plain HTTP on a LAN address - which is how the box is reached - there is no
 * `navigator.mediaDevices` at all, so the check is not "did the user say no"
 * but "does the API exist". `recordingSupported()` answers exactly that, and
 * the dialog uses it to offer picking a file instead of pretending a dead
 * button.
 *
 * **Every browser records into its own container.** Firefox does Ogg/Opus,
 * Safari MP4/AAC, Chrome WebM/Opus - and mutagen on the box has no parser for
 * WebM, so a recording from Chrome carries no duration anything server-side
 * can read. That is why the elapsed time is measured here and uploaded with
 * the file: for a WebM recording it is the only duration there is. The
 * preference order below puts the two containers the box can read tags from
 * first, so the measured value is a fallback and not the rule.
 */

/** What the recorder is doing right now. */
export type RecorderStatus = 'idle' | 'starting' | 'recording' | 'recorded';

/** Why recording is not possible - each of these needs its own sentence. */
export type RecorderError = 'unsupported' | 'denied' | 'no_microphone' | 'failed';

export interface Recording {
  /** Ready for the upload route; the extension matches the real container. */
  file: File;
  /** Measured while the microphone was open, not read from the file. */
  durationMs: number;
}

/** Containers we ask for, best first. See the note on mutagen above. */
const PREFERRED_TYPES = [
  'audio/ogg;codecs=opus',
  'audio/mp4',
  'audio/webm;codecs=opus',
  'audio/webm',
];

/** How often the elapsed time is refreshed - and the auto-stop is checked. */
const TICK_MS = 200;

/**
 * Is there a microphone API at all?
 *
 * False on every plain-HTTP origin except localhost, which is the normal case
 * for a box on the home network - see the module note.
 */
export const recordingSupported = (): boolean =>
  typeof window !== 'undefined' &&
  typeof window.MediaRecorder !== 'undefined' &&
  typeof navigator !== 'undefined' &&
  typeof navigator.mediaDevices?.getUserMedia === 'function';

/** The first container this browser can actually record, or undefined. */
const pickMimeType = (): string | undefined => {
  if (typeof window.MediaRecorder?.isTypeSupported !== 'function') return undefined;
  return PREFERRED_TYPES.find((type) => window.MediaRecorder.isTypeSupported(type));
};

/** File extension for what the recorder says it produced. */
export const extensionFor = (mimeType: string): string => {
  const base = (mimeType.split(';')[0] ?? '').trim().toLowerCase();
  switch (base) {
    case 'audio/ogg':
      return 'ogg';
    case 'audio/mp4':
    case 'audio/aac':
      return 'm4a';
    case 'audio/mpeg':
      return 'mp3';
    case 'audio/wav':
    case 'audio/x-wav':
      return 'wav';
    default:
      // Chrome and every Chromium-based browser on Android land here.
      return 'webm';
  }
};

interface UseAudioRecorderOptions {
  /** Hard stop, so a forgotten recording cannot fill the SD card. */
  maxDurationMs: number;
}

export function useAudioRecorder({ maxDurationMs }: UseAudioRecorderOptions) {
  const [status, setStatus] = useState<RecorderStatus>('idle');
  const [error, setError] = useState<RecorderError | null>(null);
  const [elapsedMs, setElapsedMs] = useState(0);
  const [recording, setRecording] = useState<Recording | null>(null);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const tickRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAtRef = useRef(0);

  /** Release the microphone. The browser shows a recording indicator until
   *  every track is stopped, so this must run on every exit path. */
  const releaseStream = useCallback(() => {
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
  }, []);

  const clearTick = useCallback(() => {
    if (tickRef.current !== null) {
      clearInterval(tickRef.current);
      tickRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    clearTick();
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      // The blob is assembled in the recorder's own onstop handler below.
      recorder.stop();
    }
  }, [clearTick]);

  const start = useCallback(async () => {
    if (!recordingSupported()) {
      setError('unsupported');
      return;
    }
    setError(null);
    setRecording(null);
    setElapsedMs(0);
    setStatus('starting');

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        // A spoken message, not music: the browser's own cleanup is welcome.
        audio: { echoCancellation: true, noiseSuppression: true },
      });
    } catch (cause) {
      const name = cause instanceof Error ? cause.name : '';
      setStatus('idle');
      setError(
        name === 'NotAllowedError' || name === 'SecurityError'
          ? 'denied'
          : name === 'NotFoundError' || name === 'OverconstrainedError'
            ? 'no_microphone'
            : 'failed',
      );
      return;
    }

    streamRef.current = stream;
    const mimeType = pickMimeType();
    let recorder: MediaRecorder;
    try {
      recorder = new MediaRecorder(stream, mimeType ? { mimeType } : undefined);
    } catch {
      releaseStream();
      setStatus('idle');
      setError('failed');
      return;
    }
    recorderRef.current = recorder;

    const chunks: BlobPart[] = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstop = () => {
      clearTick();
      releaseStream();
      // recorder.mimeType is what the browser really used, which is not
      // always what was asked for.
      const type = recorder.mimeType || mimeType || 'audio/webm';
      const blob = new Blob(chunks, { type });
      const durationMs = Math.min(maxDurationMs, Math.round(performance.now() - startedAtRef.current));
      setElapsedMs(durationMs);
      setRecording({
        file: new File([blob], `message.${extensionFor(type)}`, { type }),
        durationMs,
      });
      setStatus('recorded');
      recorderRef.current = null;
    };
    recorder.onerror = () => {
      clearTick();
      releaseStream();
      recorderRef.current = null;
      setStatus('idle');
      setError('failed');
    };

    startedAtRef.current = performance.now();
    recorder.start();
    setStatus('recording');

    tickRef.current = setInterval(() => {
      const elapsed = performance.now() - startedAtRef.current;
      setElapsedMs(elapsed);
      if (elapsed >= maxDurationMs) stop();
    }, TICK_MS);
  }, [clearTick, maxDurationMs, releaseStream, stop]);

  /** Throw the take away and start over - the recording itself is not kept. */
  const reset = useCallback(() => {
    clearTick();
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== 'inactive') {
      recorder.onstop = null;
      recorder.stop();
    }
    recorderRef.current = null;
    releaseStream();
    setRecording(null);
    setElapsedMs(0);
    setError(null);
    setStatus('idle');
  }, [clearTick, releaseStream]);

  // Closing the dialog mid-recording must not leave the microphone open.
  useEffect(() => reset, [reset]);

  return { status, error, elapsedMs, recording, start, stop, reset };
}
