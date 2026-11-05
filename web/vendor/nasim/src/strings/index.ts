import { reactAria } from './react-aria';

// Only the words Nasim itself shows; a screen passes its own copy to the components as props.
export const t = {
  common: {
    back: 'بازگشت',
    cancel: 'انصراف',
    clearSearch: 'پاک کردن جست‌وجو',
    close: 'بستن',
    confirm: 'تأیید',
    copied: 'کپی شد',
    copy: 'کپی',
    copyFailed: 'کپی نشد',
    copyFailedHint: 'متن انتخاب شد؛ آن را دستی کپی کنید.',
    copyFailedByHand: 'کپی نشد؛ مقدار را دستی انتخاب و کپی کنید.',
    copyOf: (label: string) => `کپی ${label}`,
    loading: 'در حال بارگذاری',
    retry: 'تلاش دوباره',
    selectPlaceholder: 'انتخاب کنید',
  },
  toast: {
    region: 'اعلان‌ها',
  },
  shell: {
    openMenu: 'باز کردن منو',
    closeMenu: 'بستن منو',
  },
  pager: {
    label: 'صفحه‌بندی',
    previous: 'صفحه قبل',
    next: 'صفحه بعد',
    page: (page: string) => `صفحه ${page}`,
    pageOf: (page: string, total: string) => `صفحه ${page} از ${total}`,
    refreshing: 'در حال به‌روزرسانی',
  },
  tabs: {
    scrollStart: 'پیمایش زبانه‌ها به چپ',
    scrollEnd: 'پیمایش زبانه‌ها به راست',
    scrollUp: 'پیمایش زبانه‌ها به بالا',
    scrollDown: 'پیمایش زبانه‌ها به پایین',
  },
  sortableList: {
    moveUp: (name: string) => `بردن ${name} به بالا`,
    moveDown: (name: string) => `بردن ${name} به پایین`,
    moved: (name: string, position: string, total: string) =>
      `${name} در جایگاه ${position} از ${total} قرار گرفت.`,
  },
  calendar: {
    // HeroUI words this button itself («Mehr 1405 AP, year selector»); the month and year stay visible
    selectYear: 'انتخاب سال',
  },
  stepper: {
    position: (step: string, total: string, name: string) =>
      `مرحله ${step} از ${total}: ${name}`,
  },
  state: {
    errorTitle: 'بارگذاری انجام نشد',
    errorMessage: 'اتصال اینترنت را بررسی کنید و دوباره تلاش کنید.',
    contactSupport: 'تماس با پشتیبانی',
    trackingCode: 'کد پیگیری',
    retryIn: (seconds: string) => `تلاش دوباره (${seconds} ثانیه)`,
    emptyTable: 'موردی برای نمایش وجود ندارد.',
    offline:
      'اتصال اینترنت برقرار نیست. پس از برقراری اتصال، اطلاعات به‌روز می‌شود.',
  },
  reactAria,
};

// Persian digits and grouping come from Intl, never from string replacement.
const numbers = new Intl.NumberFormat('fa-IR');

export function formatNumber(value: number): string {
  return numbers.format(value);
}
