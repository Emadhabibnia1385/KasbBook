import type { ReactNode } from 'react';
import { tv } from 'tailwind-variants';

const cover = tv({
  base: 'grid aspect-video place-items-center overflow-hidden bg-linear-to-br from-accent/25 to-accent/10 text-accent [&>svg]:size-10',
});

type CoverProps = {
  /** The picture; none yet or none at all shows the placeholder. */
  src?: string | null | undefined;
  /** The kind of thing it stands for (a category, a product): drawn on the placeholder. */
  icon: ReactNode;
  className?: string;
};

/** A 16:9 picture box that keeps its shape with or without the picture. */
export function Cover({ src, icon, className }: CoverProps) {
  return (
    <div aria-hidden={src ? undefined : true} className={cover({ className })}>
      {src ? (
        <img
          src={src}
          alt=""
          loading="lazy"
          decoding="async"
          className="size-full object-cover"
        />
      ) : (
        icon
      )}
    </div>
  );
}
