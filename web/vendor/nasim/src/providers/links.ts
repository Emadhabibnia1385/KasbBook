// An address with a scheme or a //host leaves the app, and the router must not rewrite it.
const EXTERNAL = /^([a-z][a-z\d+.-]*:|\/\/)/i;

export const isExternalHref = (to: string | undefined): boolean =>
  to !== undefined && EXTERNAL.test(to);
