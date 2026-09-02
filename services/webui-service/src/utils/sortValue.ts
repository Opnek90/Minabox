/**
 * Epoch millis for a nullable timestamp, so it can be compared like any other
 * sort value. "Never" becomes 0 and therefore sorts first when ascending.
 */
export const timeValue = (value: string | null | undefined): number =>
  value ? new Date(value).getTime() : 0;
