import { type ReactNode, useState } from 'react';
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  Chip,
  CloseButton,
  ColorArea,
  ColorPicker,
  ColorSlider,
  ColorSwatch,
  Label,
  LinkButton,
  ListBox,
  PageHeader,
  ProgressBar,
  Select,
  Separator,
  Skeleton,
  Spinner,
  toast,
  Tooltip,
} from '..';

export function Section({
  title,
  children,
}: {
  title: string;
  children: ReactNode;
}) {
  return (
    <section className="flex flex-col gap-4">
      <PageHeader as="h2" size="section" title={title} />
      {children}
    </section>
  );
}

const VARIANTS = [
  'primary',
  'secondary',
  'tertiary',
  'outline',
  'ghost',
  'danger',
] as const;
const STATUSES = ['default', 'accent', 'success', 'warning', 'danger'] as const;

export function PrimitivesDemo() {
  const [pending, setPending] = useState(false);
  return (
    <Section title="دکمه‌ها و نشانه‌ها">
      <div className="flex flex-wrap gap-2">
        {VARIANTS.map((variant) => (
          <Button key={variant} variant={variant}>
            {variant}
          </Button>
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <Button size="sm">کوچک</Button>
        <Button size="md">متوسط</Button>
        <Button size="lg">بزرگ (۴۴ پیکسل)</Button>
        <Button isDisabled>غیرفعال</Button>
        <Button
          isPending={pending}
          onPress={() => {
            setPending(true);
            setTimeout(() => setPending(false), 1500);
          }}
        >
          {({ isPending }) => (
            <>
              {isPending ? <Spinner color="current" size="sm" /> : null}
              در حال ارسال
            </>
          )}
        </Button>
        <LinkButton href="#" variant="outline">
          پیوند دکمه‌ای
        </LinkButton>
        <CloseButton />
        <Tooltip>
          <Button variant="ghost">راهنما</Button>
          <Tooltip.Content>متن راهنمای کوتاه</Tooltip.Content>
        </Tooltip>
      </div>
      <div className="flex flex-wrap items-center gap-2">
        {STATUSES.map((color) => (
          <Chip key={color} color={color} variant="soft">
            {color}
          </Chip>
        ))}
        <Spinner size="sm" />
        <Spinner />
        <Spinner size="lg" color="success" />
        <Badge.Anchor>
          <Avatar>
            <Avatar.Fallback>نس</Avatar.Fallback>
          </Avatar>
          <Badge color="danger" size="sm">
            ۳
          </Badge>
        </Badge.Anchor>
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        {STATUSES.map((status) => (
          <Alert key={status} status={status}>
            <Alert.Indicator />
            <Alert.Content>
              <Alert.Title>وضعیت {status}</Alert.Title>
              <Alert.Description>
                پیام کوتاهی که بگوید بعدش چه کنید.
              </Alert.Description>
            </Alert.Content>
          </Alert>
        ))}
      </div>
      <div className="grid gap-3 sm:grid-cols-2">
        <Card>
          <Card.Header>
            <Card.Title>سرویس ۳۰ روزه</Card.Title>
            <Card.Description>۵۰ گیگابایت، دو کاربر همزمان</Card.Description>
          </Card.Header>
          <Card.Content>
            <ProgressBar value={62}>
              <Label>مصرف</Label>
              <ProgressBar.Output />
              <ProgressBar.Track>
                <ProgressBar.Fill />
              </ProgressBar.Track>
            </ProgressBar>
          </Card.Content>
          <Card.Footer>
            <Button size="sm" variant="secondary">
              تمدید
            </Button>
          </Card.Footer>
        </Card>
        <Card variant="secondary" aria-busy>
          <Skeleton className="h-4 w-1/2 rounded-md" />
          <Skeleton className="h-4 w-full rounded-md" />
          <Skeleton className="h-4 w-3/4 rounded-md" />
          <Separator />
          <Skeleton className="h-9 w-24 rounded-full" />
        </Card>
      </div>
      <div className="flex flex-wrap gap-2">
        <Button variant="secondary" onPress={() => toast('پیام ساده')}>
          اعلان ساده
        </Button>
        <Button variant="secondary" onPress={() => toast.success('ذخیره شد')}>
          موفق
        </Button>
        <Button
          variant="secondary"
          onPress={() => {
            const id = toast.danger('پرداخت انجام نشد', {
              description: 'موجودی کیف پول کافی نیست.',
              timeout: 8000,
              actionProps: {
                children: 'شارژ کیف پول',
                onPress: () => toast.close(id),
              },
            });
          }}
        >
          خطا با دکمه
        </Button>
      </div>
      <Select className="max-w-64">
        <Label>پروتکل</Label>
        <Select.Trigger>
          <Select.Value />
          <Select.Indicator />
        </Select.Trigger>
        <Select.Popover>
          <ListBox>
            <ListBox.Item id="vless" textValue="VLESS">
              VLESS
              <ListBox.ItemIndicator />
            </ListBox.Item>
            <ListBox.Item id="wireguard" textValue="WireGuard">
              WireGuard
              <ListBox.ItemIndicator />
            </ListBox.Item>
          </ListBox>
        </Select.Popover>
      </Select>
      <ColorPicker defaultValue="#c3e52a">
        <ColorPicker.Trigger>
          <ColorSwatch size="lg" />
          <Label>رنگ فروشگاه</Label>
        </ColorPicker.Trigger>
        <ColorPicker.Popover>
          <ColorArea
            colorSpace="hsb"
            xChannel="saturation"
            yChannel="brightness"
          >
            <ColorArea.Thumb />
          </ColorArea>
          <ColorSlider channel="hue" colorSpace="hsb">
            <Label>طیف رنگ</Label>
            <ColorSlider.Track>
              <ColorSlider.Thumb />
            </ColorSlider.Track>
          </ColorSlider>
        </ColorPicker.Popover>
      </ColorPicker>
    </Section>
  );
}
