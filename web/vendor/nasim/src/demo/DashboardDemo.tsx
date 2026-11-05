import { useState } from 'react';
import {
  Button,
  Collapsible,
  CopyButton,
  type DataColumn,
  DataTable,
  Modal,
  Notice,
  OfflineBanner,
  Pager,
  SectionCard,
  SkeletonRows,
  StatCard,
  StatusChip,
  Tabs,
  ThemeToggle,
} from '..';
import { Section } from './PrimitivesDemo';

type Row = { id: string; name: string; amount: string };

const ROWS: Row[] = [
  { id: 'a', name: 'سفارش ۱۰۰۱', amount: '۱٬۵۰۰٬۰۰۰' },
  { id: 'b', name: 'سفارش ۱۰۰۲', amount: '۲۵۰٬۰۰۰' },
];

const COLUMNS: DataColumn<Row>[] = [
  { id: 'name', header: 'سفارش', cell: (row) => row.name, isRowHeader: true },
  {
    id: 'status',
    header: 'وضعیت',
    cell: (row) =>
      row.id === 'a' ? (
        <StatusChip tone="success" label="پرداخت‌شده" size="sm" />
      ) : (
        <StatusChip tone="info" label="در انتظار واریز" size="sm" />
      ),
  },
  {
    id: 'amount',
    header: 'مبلغ (تومان)',
    cell: (row) => row.amount,
    align: 'end',
  },
];

// The parts a dashboard repeats on every screen: states, cards, a table, a dialog, tabs.
export function DashboardDemo() {
  const [open, setOpen] = useState(false);
  const [page, setPage] = useState(2);
  const [tab, setTab] = useState('sales');
  return (
    <Section title="داشبورد">
      <div className="flex flex-wrap items-center gap-3">
        <StatusChip tone="success" label="پرداخت‌شده" />
        <StatusChip tone="warning" label="نیازمند بررسی" />
        <StatusChip tone="danger" label="ناموفق" />
        <StatusChip tone="info" label="در انتظار واریز" />
        <StatusChip tone="neutral" label="منقضی‌شده" />
        <ThemeToggle lightLabel="حالت روشن" darkLabel="حالت تیره" />
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Notice tone="info" title="اطلاعات">
          پیام برای آگاهی.
        </Notice>
        <Notice tone="success" role="status">
          انجام شد.
        </Notice>
        <Notice tone="warning" title="هشدار">
          این کار به اعتبار شما وابسته است.
        </Notice>
        <Notice tone="danger" role="alert" title="خطا">
          پرداخت انجام نشد.
        </Notice>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <StatCard
          label="فروش موفق"
          value="۱۲٬۴۰۰٬۰۰۰ تومان"
          hint="۳۰ روز گذشته"
          footer={
            <p className="text-xs text-muted">نسبت به ماه قبل: ۱۲٪ بیشتر</p>
          }
        />
        <StatCard label="اعتبار قابل استفاده" value="۲۰۰٬۰۰۰ تومان" />
      </div>
      <SectionCard
        title="کارت مقصد"
        description="فروش‌های شما مستقیم به این کارت واریز می‌شود."
        actions={<Button size="sm">افزودن کارت</Button>}
      >
        <div className="flex flex-col gap-3">
          <CopyButton value="6037991234567893" label="کپی شماره کارت" />
          <Collapsible
            title="تنظیمات پیشرفته"
            description="سقف روزانه و زمان‌بندی"
          >
            <p className="text-sm text-muted">فقط در صورت نیاز تغییر دهید.</p>
          </Collapsible>
        </div>
      </SectionCard>
      <Tabs
        label="بخش‌ها"
        selectedKey={tab}
        onSelectionChange={setTab}
        items={[
          {
            id: 'sales',
            label: 'فروش',
            content: (
              <DataTable
                ariaLabel="فاکتورها"
                columns={COLUMNS}
                rows={ROWS}
                getRowId={(row) => row.id}
                status="ready"
                pagination={{ page, pageCount: 4, onPageChange: setPage }}
              />
            ),
          },
          {
            id: 'empty',
            label: 'خالی',
            content: (
              <DataTable
                ariaLabel="فاکتورها"
                columns={COLUMNS}
                rows={[]}
                getRowId={(row) => row.id}
                status="ready"
                emptyTitle="هنوز فاکتوری ندارید"
                empty="پس از ساخت اولین فاکتور اینجا می‌آید."
              />
            ),
          },
          {
            id: 'loading',
            label: 'در حال بارگذاری',
            content: <SkeletonRows rows={2} />,
          },
        ]}
      />
      <Pager page={2} hasNext onPrevious={() => {}} onNext={() => {}} />
      <OfflineBanner />
      <Button variant="secondary" onPress={() => setOpen(true)}>
        بازکردن پنجره
      </Button>
      <Modal
        isOpen={open}
        onOpenChange={setOpen}
        title="دعوت عضو تیم"
        footer={
          <>
            <Button variant="tertiary" onPress={() => setOpen(false)}>
              انصراف
            </Button>
            <Button onPress={() => setOpen(false)}>ارسال دعوت</Button>
          </>
        }
      >
        <p className="text-sm text-muted">
          دعوت‌نامه با پیوند یک‌بارمصرف ارسال می‌شود.
        </p>
      </Modal>
    </Section>
  );
}
