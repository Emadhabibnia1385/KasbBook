/** The KasbBook mark, in the colouring that reads on the current theme (see `.brand-on-*` in index.css). */
export function BrandMark({ className }: { className?: string }) {
	return (
		<>
			<img
				src="/brand/logo-icon-light.png"
				alt=""
				className={`brand-on-light ${className ?? ""}`}
				decoding="async"
			/>
			<img
				src="/brand/logo-icon-dark.png"
				alt=""
				className={`brand-on-dark ${className ?? ""}`}
				decoding="async"
			/>
		</>
	);
}
