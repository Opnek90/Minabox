# Where a setting lives

Rules for the three pages that carry configuration - Player, Parent dashboard,
Settings - and the map of the Settings page. This is the document to read
before adding a field, a section or a group; the index in
`src/config/settingsIndex.ts` is the code that follows it.

The settings area grew field by field over a year, and each addition was placed
sensibly on its own. The sum was not: a night has settings in four places, a
password can be changed in two sections that sit next to each other, and one
form used to be reachable from two pages. The structure below replaces
"sensible on its own" with a small set of rules that decide the place of a
setting before it is built.

## Three pages, three time horizons

The pages are not split by topic but by **how often a parent touches what is on
them**. That is the question to ask first, and it usually settles the page.

| Page | Horizon | What belongs there | Test |
| --- | --- | --- | --- |
| **Player** | now | actions that change *this* playback: volume, sleep timer, shuffle, repeat | "Does it end when the music ends?" |
| **Parent dashboard** | this week | the rules the box enforces on the child, and what the child did: listening times, daily limit, volume limits, the evening fade; statistics and history | "Would a parent change it on a Tuesday because of how Monday went?" |
| **Settings** | once | how the box is built and behaves; changed after setting it up and then rarely | "Would it be wrong a month later?" |

A value that is a *rule for the child* goes to the dashboard even when it is
technically a configuration - the volume limit is the model. A value that is
*about the box* goes to Settings even when a parent could in principle tweak it
weekly - the default sleep timer length is the model.

## The rules

1. **One place per value.** Every setting is edited in exactly one section.
   Another page may *point* at it - a search hit, a "Settings →" link, a deep
   link - but never shows a second form for it. Two forms for one value are
   two ideas of the current state, and they disagree the moment one of them
   is saved.

2. **Grouped by the user's question, never by the service.** Which container
   or process owns a value says nothing about where it is shown. A group name
   must not be the name of a service, a protocol or a file. Test: would a
   parent with no IT background use that word to describe what they are
   looking for?

3. **Editing, reading and doing are three different things.** A section is
   one of: a *form* (fields that are saved), a *status* (values that are only
   read), or *actions* (buttons that do something to the box). The only
   action allowed inside a form is "test this". Status and actions each have
   their own group so nobody looks for a switch in a page of buttons.

4. **A topic is one section, whatever it touches.** When a new field belongs
   to an existing everyday topic, it joins that section - even if it is
   handled by a different service than the fields already there. Splitting a
   topic across sections because the backend is split is exactly the pattern
   that produced the patchwork.

5. **An addon is switched on the addons page and configured where its topic
   is.** The addons table adds, removes and updates. The settings of an addon
   sit in the group of the question they answer (announcements under Sound,
   import domains under Library), and the addon row links there. The gear
   button is a link, not a second form (rule 1).

6. **Search and deep links are the only second way in.** `searchKeys` on a
   section and `sectionDomId` are how someone reaches a setting without knowing
   the group. That is what makes rule 1 affordable: nobody has to know the map.

7. **A new group needs a question nobody else answers.** Before adding a
   group, try every existing one. A group is not "the settings of service X";
   it is the answer to "where do I look for …". One section is enough for a
   group when its question is genuinely separate ("Appearance" is), not when
   it merely has nowhere else to go.

8. **Names are everyday words, in both languages.** Section and group titles
   describe what the user gets, not the mechanism: "Card reader", not "RFID";
   "Lights", not "LED service"; "Wi-Fi & address", not "Network configuration".

## The map

The groups of the Settings page, in the order they are shown, under three
headings that structure the navigation (a sidebar on desktop, headed lists on a
phone) without adding a level to the content.

### Listening — what the child experiences

| Group | Sections | Kind |
| --- | --- | --- |
| **Playback** | When a card is placed · Falling asleep (default timer length) | form |
| **Sound** | Speakers & headphones (output, Bluetooth, resume on start) · Announcements | form |
| **Library** | Music folder · Upload limit · Media import: allowed domains · From USB stick · Cover & metadata (backfill) | form / action |
| **Appearance** | Language & colours (logo, language, theme, font size, accent) | form |

### The box — what is attached and inside

| Group | Sections | Kind |
| --- | --- | --- |
| **Devices** | Card reader · Buttons & dial · Lights · Display · Status LED of the board | form (each hangs off its addon, except the board LED) |
| **Addons** | What this box can do (the table) | action |
| **Network** | Wi-Fi & address (status, Wi-Fi, hostname, IPv4) | form / status |

### Administration — what an adult does rarely

| Group | Sections | Kind |
| --- | --- | --- |
| **Security** | Web interface (password, protected areas) · Remote access via SSH (switch, Linux password) | form |
| **Maintenance** | Backup & data (backup, restore, how long listening statistics are kept) · Updates · Restart & reset · Run setup again | action |
| **System** | Advanced (device id, log level, MQTT) · Status & logs | form / status |

## What moves, and why

Two of these landed already, alongside this document, because they were small
and the addons page was already being touched:

- **Gear button on an addon row.** Used to open the addon's form in a dialog -
  a second place to edit the same value (rule 1). Now it is a link to the
  section that owns it (`?section=<key>`, the same deep link the search and
  the CommandPalette use).
- **Status LED of the board** (the Raspberry Pi's own green/red LED). Used to
  sit inside *Lights*, which disappears without the LED addon - so a box
  without external LEDs could not turn its own status light off either. It is
  not part of that addon (rule 4), so it now has its own section under
  Devices, shown regardless of which addons are installed.

Still to do, as their own change:

| Setting | Today | Target | Rule |
| --- | --- | --- | --- |
| Statistics retention (weeks) | Dashboard → Time & rules | Maintenance → Backup & data | horizon: set once; it is about data, not about the child |
| Web password + protected areas, SSH switch + Linux password | one section "Passwords & access" with both passwords in a row | two sections: *Web interface*, *Remote access via SSH* | 3, 4 - two passwords for two things must not look like one |
| Ten tabs across the top | one row of ten | sidebar with the three headings above; accordion with the same headings on a phone | ten peers are a list, not a structure |

What deliberately stays where it is:

- **Volume limits and the evening fade stay on the dashboard.** They are rules
  for the child, and the horizon test says "this week". The output device stays
  under Sound - that is about the box.
- **Announcements stay under Sound**, where a parent looks for a volume; the
  addon row links there.
- **The default sleep-timer length stays under Playback.** Starting a timer is
  the Player's job; how long it runs by default is set once.
- **USB import stays under Library** although it is an action: the user's
  question is "how do I get music onto the box", and that is the Library.
- **Running the setup wizard again stays under Maintenance**: it is an action
  on the whole box, next to backup and reset.

## Guards

Rules that live only in a document erode. Two of them can be checked:

- **One component, one section.** A test over `SECTION_CONTENT` asserts that no
  React component type is rendered by more than one section, and that every
  section in `settingsIndex` has content. This is the test that would have
  caught the addon dialog.
- **Every section is searchable.** A test asserts that every section carries at
  least one `searchKey` and that each key resolves in both locales (the i18n
  guard already checks the second half).

## Night, as an open question

The evening is the one topic this map cannot fully tidy, because the values
are not only in different sections but in different *models*: the display has
its own `night_from` / `night_to`, the listening times have theirs, and the
evening fade has a duration. From the user's side there is one evening. A
single night window that display, fade and listening times all read would
remove three settings and one contradiction, but it is a backend change with
a migration behind it, and it does not belong to a restructuring of the page.
It is noted here so it is not solved a fourth time in a fourth place.
