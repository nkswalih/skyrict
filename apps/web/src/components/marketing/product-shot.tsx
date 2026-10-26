import Image from "next/image";

import { cn } from "@/lib/utils";

type ProductShotProps = {
    src: string;
    alt: string;
    className?: string;
    imageClassName?: string;
    priority?: boolean;
    sizes?: string;
    tone?: "light" | "dark";
};

function ProductShot({
    src,
    alt,
    className,
    imageClassName,
    priority = false,
    sizes = "(min-width: 1024px) 50vw, 100vw",
    tone = "light",
}: ProductShotProps) {
    return (
        <figure className={cn("min-w-0", className)}>
            <div
                className={cn(
                    "overflow-hidden rounded-[1.05rem] border bg-white",
                    tone === "dark"
                        ? "border-marketing-paper/15 shadow-[0_30px_90px_-40px_rgba(0,0,0,0.75)]"
                        : "border-marketing-ink/10 shadow-[0_24px_70px_-40px_rgba(10,47,62,0.28)]",
                )}
            >
                <Image
                    src={src}
                    alt={alt}
                    width={3024}
                    height={1964}
                    priority={priority}
                    sizes={sizes}
                    className={cn("block h-auto w-full", imageClassName)}
                />
            </div>
        </figure>
    );
}

export { ProductShot };
