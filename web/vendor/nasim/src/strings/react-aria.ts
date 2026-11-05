// Persian replacements for React Aria's English labels; keys it does not list stay English.
// A message is a string, or a function of the variables the call passes (typed where it is written).
type Message =
  | string
  | ((args: never, formatter: { number(value: number): string }) => string);
export type Dictionary = Record<string, Record<string, Message>>;

export const reactAria = {
  'react-aria-components': {
    selectPlaceholder: 'انتخاب کنید',
    tableResizer: 'تغییر اندازه',
    dropzoneLabel: 'محل رها کردن فایل',
    colorSwatchPicker: 'نمونه‌های رنگ',
  },
  '@react-aria/overlays': {
    dismiss: 'بستن پنجره',
  },
  '@react-aria/toast': {
    close: 'بستن',
    notifications: (args: { count: number }, formatter) =>
      `${formatter.number(args.count)} اعلان`,
  },
  '@react-aria/numberfield': {
    decrease: (args: { fieldLabel: string }) => `کاهش ${args.fieldLabel}`,
    increase: (args: { fieldLabel: string }) => `افزایش ${args.fieldLabel}`,
    numberField: 'فیلد عددی',
  },
  '@react-aria/spinbutton': {
    Empty: 'خالی',
  },
  '@react-aria/searchfield': {
    'Clear search': 'پاک کردن جست‌وجو',
  },
  '@react-aria/combobox': {
    focusAnnouncement: (
      args: {
        isGroupChange: boolean;
        groupTitle: string;
        groupCount: number;
        optionText: string;
        isSelected: boolean;
      },
      formatter,
    ) =>
      `${
        args.isGroupChange
          ? `وارد گروه ${args.groupTitle} شدید که ${formatter.number(args.groupCount)} گزینه دارد. `
          : ''
      }${args.optionText}${args.isSelected ? '، انتخاب شده' : ''}`,
    countAnnouncement: (args: { optionCount: number }, formatter) =>
      `${formatter.number(args.optionCount)} گزینه در دسترس است.`,
    selectedAnnouncement: (args: { optionText: string }) =>
      `${args.optionText}، انتخاب شد`,
    buttonLabel: 'نمایش پیشنهادها',
    listboxLabel: 'پیشنهادها',
  },
  '@react-aria/autocomplete': {
    collectionLabel: 'پیشنهادها',
  },
  '@react-aria/breadcrumbs': {
    breadcrumbs: 'مسیر صفحه',
  },
  '@react-aria/menu': {
    longPressMessage:
      'برای باز شدن منو، لمس طولانی کنید یا Alt و فلش پایین را بزنید',
  },
  '@react-aria/tag': {
    removeDescription: 'برای حذف برچسب، Delete را بزنید.',
    removeButtonLabel: 'حذف',
  },
  '@react-aria/tree': {
    expand: 'باز کردن',
    collapse: 'بستن',
  },
  '@react-aria/table': {
    select: 'انتخاب',
    selectAll: 'انتخاب همه',
    sortable: 'ستون قابل مرتب‌سازی',
    ascending: 'صعودی',
    descending: 'نزولی',
    ascendingSort: (args: { columnName: string }) =>
      `مرتب‌شده بر اساس ستون ${args.columnName} به‌صورت صعودی`,
    descendingSort: (args: { columnName: string }) =>
      `مرتب‌شده بر اساس ستون ${args.columnName} به‌صورت نزولی`,
    columnSize: (args: { value: number }) => `${args.value} پیکسل`,
    resizerDescription: 'برای شروع تغییر اندازه، Enter را بزنید',
    expand: 'باز کردن',
    collapse: 'بستن',
  },
  '@react-aria/grid': {
    deselectedItem: (args: { item: string }) => `${args.item} انتخاب نشده است.`,
    select: 'انتخاب',
    selectedCount: (args: { count: number }, formatter) =>
      args.count === 0
        ? 'هیچ موردی انتخاب نشده است.'
        : `${formatter.number(args.count)} مورد انتخاب شده است.`,
    selectedAll: 'همهٔ موارد انتخاب شدند.',
    selectedItem: (args: { item: string }) => `${args.item} انتخاب شد.`,
    longPressToSelect: 'برای ورود به حالت انتخاب، لمس طولانی کنید.',
  },
  '@react-aria/gridlist': {
    hasActionAnnouncement: 'این ردیف عملیات دارد',
    hasLinkAnnouncement: (args: { link: string }) =>
      `این ردیف پیوند دارد: ${args.link}`,
  },
  '@react-aria/dnd': {
    dragItem: (args: { itemText: string }) => `کشیدن ${args.itemText}`,
    dragSelectedItems: (args: { count: number }, formatter) =>
      `کشیدن ${formatter.number(args.count)} مورد انتخاب‌شده`,
    dragDescriptionKeyboard: 'برای شروع جابه‌جایی، Enter را بزنید.',
    dragDescriptionKeyboardAlt: 'برای شروع جابه‌جایی، Alt و Enter را بزنید.',
    dragDescriptionTouch: 'برای شروع جابه‌جایی، دو بار ضربه بزنید.',
    dragDescriptionVirtual: 'برای شروع جابه‌جایی، کلیک کنید.',
    dragDescriptionLongPress: 'برای شروع جابه‌جایی، لمس طولانی کنید.',
    dragSelectedKeyboard: (args: { count: number }, formatter) =>
      `برای جابه‌جایی ${formatter.number(args.count)} مورد انتخاب‌شده، Enter را بزنید.`,
    dragSelectedKeyboardAlt: (args: { count: number }, formatter) =>
      `برای جابه‌جایی ${formatter.number(args.count)} مورد انتخاب‌شده، Alt و Enter را بزنید.`,
    dragSelectedLongPress: (args: { count: number }, formatter) =>
      `برای جابه‌جایی ${formatter.number(args.count)} مورد انتخاب‌شده، لمس طولانی کنید.`,
    dragStartedKeyboard:
      'جابه‌جایی شروع شد. با Tab به محل رها کردن بروید، با Enter رها کنید یا با Escape لغو کنید.',
    dragStartedTouch:
      'جابه‌جایی شروع شد. به محل رها کردن بروید و دو بار ضربه بزنید.',
    dragStartedVirtual:
      'جابه‌جایی شروع شد. به محل رها کردن بروید و کلیک کنید یا Enter را بزنید.',
    endDragKeyboard: 'در حال جابه‌جایی. برای لغو، Enter را بزنید.',
    endDragTouch: 'در حال جابه‌جایی. برای لغو، دو بار ضربه بزنید.',
    endDragVirtual: 'در حال جابه‌جایی. برای لغو، کلیک کنید.',
    dropDescriptionKeyboard: 'برای رها کردن Enter و برای لغو Escape را بزنید.',
    dropDescriptionTouch: 'برای رها کردن، دو بار ضربه بزنید.',
    dropDescriptionVirtual: 'برای رها کردن، کلیک کنید.',
    dropCanceled: 'جابه‌جایی لغو شد.',
    dropComplete: 'جابه‌جایی انجام شد.',
    dropIndicator: 'نشانگر محل رها کردن',
    dropOnRoot: 'رها کردن روی',
    dropOnItem: (args: { itemText: string }) => `رها کردن روی ${args.itemText}`,
    insertBefore: (args: { itemText: string }) =>
      `قرار دادن پیش از ${args.itemText}`,
    insertBetween: (args: { beforeItemText: string; afterItemText: string }) =>
      `قرار دادن بین ${args.beforeItemText} و ${args.afterItemText}`,
    insertAfter: (args: { itemText: string }) =>
      `قرار دادن پس از ${args.itemText}`,
  },
  '@react-aria/color': {
    colorPicker: 'انتخابگر رنگ',
    twoDimensionalSlider: 'لغزندهٔ دوبعدی',
    colorNameAndValue: (args: { name: string; value: string }) =>
      `${args.name}: ${args.value}`,
    colorInputLabel: (args: { label: string; channelLabel: string }) =>
      `${args.label}، ${args.channelLabel}`,
    colorSwatch: 'نمونهٔ رنگ',
    transparent: 'شفاف',
  },
  '@react-aria/calendar': {
    previous: 'قبلی',
    next: 'بعدی',
    selectedDateDescription: (args: { date: string }) =>
      `تاریخ انتخاب‌شده: ${args.date}`,
    selectedRangeDescription: (args: { dateRange: string }) =>
      `بازهٔ انتخاب‌شده: ${args.dateRange}`,
    todayDate: (args: { date: string }) => `امروز، ${args.date}`,
    todayDateSelected: (args: { date: string }) =>
      `امروز، ${args.date}، انتخاب شد`,
    dateSelected: (args: { date: string }) => `${args.date} انتخاب شد`,
    startRangeSelectionPrompt: 'برای شروع انتخاب بازه کلیک کنید',
    finishRangeSelectionPrompt: 'برای پایان انتخاب بازه کلیک کنید',
    minimumDate: 'اولین تاریخ در دسترس',
    maximumDate: 'آخرین تاریخ در دسترس',
    dateRange: (args: { startDate: string; endDate: string }) =>
      `${args.startDate} تا ${args.endDate}`,
  },
  '@react-aria/datepicker': {
    era: 'دوره',
    year: 'سال',
    month: 'ماه',
    day: 'روز',
    hour: 'ساعت',
    minute: 'دقیقه',
    second: 'ثانیه',
    dayPeriod: 'قبل یا بعد از ظهر',
    calendar: 'تقویم',
    startDate: 'تاریخ شروع',
    endDate: 'تاریخ پایان',
    weekday: 'روز هفته',
    timeZoneName: 'منطقهٔ زمانی',
    selectedDateDescription: (args: { date: string }) =>
      `تاریخ انتخاب‌شده: ${args.date}`,
    selectedRangeDescription: (args: { startDate: string; endDate: string }) =>
      `بازهٔ انتخاب‌شده: ${args.startDate} تا ${args.endDate}`,
    selectedTimeDescription: (args: { time: string }) =>
      `زمان انتخاب‌شده: ${args.time}`,
  },
  // The name of a colour reads noun first in Persian: «قرمز پررنگ بسیار تیره».
  '@react-stately/color': {
    hue: 'ته‌رنگ',
    saturation: 'اشباع',
    lightness: 'روشنی',
    brightness: 'روشنایی',
    red: 'قرمز',
    green: 'سبز',
    blue: 'آبی',
    alpha: 'شفافیت',
    colorName: (args: { hue: string; chroma: string; lightness: string }) =>
      `${args.hue} ${args.chroma} ${args.lightness}`,
    transparentColorName: (args: {
      hue: string;
      chroma: string;
      lightness: string;
      percentTransparent: string;
    }) =>
      `${args.hue} ${args.chroma} ${args.lightness}، ${args.percentTransparent} شفاف`,
    'very dark': 'بسیار تیره',
    dark: 'تیره',
    light: 'روشن',
    'very light': 'بسیار روشن',
    pale: 'کم‌رنگ',
    grayish: 'مایل به خاکستری',
    vibrant: 'پررنگ',
    black: 'سیاه',
    white: 'سفید',
    gray: 'خاکستری',
    pink: 'صورتی',
    'pink red': 'قرمز صورتی',
    'red orange': 'قرمز نارنجی',
    brown: 'قهوه‌ای',
    orange: 'نارنجی',
    'orange yellow': 'نارنجی زرد',
    'brown yellow': 'قهوه‌ای زرد',
    yellow: 'زرد',
    'yellow green': 'زرد سبز',
    'green cyan': 'سبز فیروزه‌ای',
    cyan: 'فیروزه‌ای',
    'cyan blue': 'آبی فیروزه‌ای',
    'blue purple': 'آبی بنفش',
    purple: 'بنفش',
    'purple magenta': 'ارغوانی بنفش',
    magenta: 'ارغوانی',
    'magenta pink': 'صورتی ارغوانی',
  },
  '@react-stately/datepicker': {
    rangeUnderflow: (args: { minValue: string }) =>
      `مقدار باید ${args.minValue} یا بعد از آن باشد.`,
    rangeOverflow: (args: { maxValue: string }) =>
      `مقدار باید ${args.maxValue} یا قبل از آن باشد.`,
    rangeReversed: 'تاریخ شروع باید قبل از تاریخ پایان باشد.',
    unavailableDate: 'تاریخ انتخاب‌شده در دسترس نیست.',
  },
} satisfies Dictionary;
