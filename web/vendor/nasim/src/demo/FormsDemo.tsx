import { zodResolver } from '@hookform/resolvers/zod';
import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { z } from 'zod';
import {
  CheckboxField,
  CheckboxGroupField,
  DateTimeField,
  FormRoot,
  HexColorPicker,
  NumberField,
  RadioGroupField,
  SelectField,
  SubmitButton,
  SwitchField,
  TextAreaField,
  TextField,
  toast,
} from '..';
import { Section } from './PrimitivesDemo';

const schema = z.object({
  email: z.email({ error: 'ایمیل را درست وارد کنید؛ مثلاً name@example.com' }),
  seats: z
    .number({ error: 'تعداد کاربر را وارد کنید' })
    .min(1, { error: 'دست‌کم یک کاربر' }),
  plan: z.string({ error: 'یک پلن انتخاب کنید' }),
  renew: z.boolean(),
  note: z.string().max(200, { error: 'یادداشت حداکثر ۲۰۰ نویسه است' }),
  mode: z.string({ error: 'حالت را انتخاب کنید' }),
  scopes: z.array(z.string()).min(1, { error: 'دست‌کم یک دسترسی' }),
  expiresAt: z.string(),
  agree: z
    .boolean()
    .refine((value) => value, { error: 'باید شرایط را بپذیرید' }),
});

type Values = z.infer<typeof schema>;

const PLANS = [
  { value: '30', label: '۳۰ روزه، ۵۰ گیگابایت' },
  { value: '90', label: '۹۰ روزه، ۱۵۰ گیگابایت' },
  { value: 'sold-out', label: 'سالانه (ناموجود)', isDisabled: true },
];

export function FormsDemo() {
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: {
      email: '',
      renew: true,
      note: '',
      scopes: [],
      expiresAt: '',
      agree: false,
    },
  });
  const [brand, setBrand] = useState('#0B905D');
  return (
    <Section title="فرم‌ها">
      <FormRoot
        form={form}
        className="flex max-w-md flex-col gap-4"
        onSubmit={async () => {
          await new Promise((resolve) => setTimeout(resolve, 1500));
          toast.success('فرم ارسال شد');
        }}
      >
        <TextField
          name="email"
          type="email"
          dir="ltr"
          autoComplete="email"
          label="ایمیل"
          isRequired
        />
        <NumberField
          name="seats"
          label="تعداد کاربر"
          minValue={1}
          maxValue={10}
          isRequired
        />
        <SelectField name="plan" label="پلن" options={PLANS} isRequired />
        <SwitchField
          name="renew"
          label="تمدید خودکار"
          description="در پایان دوره از کیف پول کم می‌شود."
        />
        <TextAreaField
          name="note"
          label="یادداشت"
          description="برای شناختن سرویس بعداً."
        />
        <RadioGroupField
          name="mode"
          label="حالت"
          options={[
            {
              value: 'live',
              label: 'واقعی',
              description: 'پرداخت‌ها حساب می‌شوند.',
            },
            { value: 'sandbox', label: 'آزمایشی' },
          ]}
        />
        <CheckboxGroupField
          name="scopes"
          label="دسترسی‌ها"
          options={[
            { value: 'read', label: 'خواندن' },
            { value: 'write', label: 'نوشتن' },
          ]}
        />
        <DateTimeField
          name="expiresAt"
          label="مهلت"
          calendarLabel="تقویم"
          timeLabel="ساعت"
          clearLabel="پاک کردن"
        />
        <HexColorPicker
          value={brand}
          onChange={setBrand}
          label="رنگ برند"
          hueLabel="فام"
          presetsLabel="رنگ‌های آماده"
          presets={['#0B905D', '#245BAA', '#B42338']}
          fallback="#0B905D"
        />
        <CheckboxField name="agree">شرایط استفاده را می‌پذیرم</CheckboxField>
        <SubmitButton>ارسال</SubmitButton>
      </FormRoot>
    </Section>
  );
}
