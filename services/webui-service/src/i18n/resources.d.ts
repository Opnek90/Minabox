// Leitet die Typisierung von t() aus den deutschen Locale-Dateien ab. Die
// check-locales.mjs-Pruefung stellt sicher, dass de/en dieselben Keys haben -
// deshalb reicht eine Sprache als Typ-Quelle fuer beide.
import common from '../../public/locales/de/common.json';
import player from '../../public/locales/de/player.json';
import rfid from '../../public/locales/de/rfid.json';
import media from '../../public/locales/de/media.json';
import admin from '../../public/locales/de/admin.json';
import errors from '../../public/locales/de/errors.json';
import setup from '../../public/locales/de/setup.json';

declare module 'i18next' {
  interface CustomTypeOptions {
    defaultNS: 'common';
    resources: {
      common: typeof common;
      player: typeof player;
      rfid: typeof rfid;
      media: typeof media;
      admin: typeof admin;
      errors: typeof errors;
      setup: typeof setup;
    };
  }
}
