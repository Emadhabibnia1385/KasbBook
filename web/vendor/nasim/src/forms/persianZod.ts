import { config } from 'zod/v4/core';
import persian from 'zod/v4/locales/fa.js';

// A fallback only: a schema's own messages win. It lives with the forms, not in the provider, so a page
// without a form does not ship Zod.
config(persian());
