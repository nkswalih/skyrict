import Image from "next/image";

import { cn } from "@/lib/utils";

type ProductFigureProps = {
    src: string;
    alt: string;
    width: number;
    height: number;
    mobileSrc?: string;
    mobileWidth?: number;
    mobileHeight?: number;
    className?: string;
    frameClassName?: string;
    priority?: boolean;
    sizes?: string;
    mobileSizes?: string;
};

/**
 * A focused crop of the Skyrict workspace, framed without chrome so the
 * interface stays readable.
 */
function ProductFigure({
    src,
    alt,
    width,
    height,
    mobileSrc,
    mobileWidth,
    mobileHeight,
    className,
    frameClassName,
    priority = false,
    sizes = "(min-width: 1024px) 50vw, 100vw",
    mobileSizes = "100vw",
}: ProductFigureProps) {
    return (
        <figure className={cn("min-w-0", className)}>
            <div
                className={cn(
                    "relative overflow-hidden rounded-[1.15rem] border border-marketing-ink/10 bg-white shadow-[0_26px_80px_-54px_rgba(10,47,62,0.5)]",
                    frameClassName,
                )}
            >
                <div className={cn(mobileSrc && "hidden sm:block")}>
                    <Image
                        src={src}
                        alt={alt}
                        width={width}
                        height={height}
                        priority={priority}
                        sizes={sizes}
                        className="block h-auto w-full"
                    />
                </div>
                {mobileSrc ? (
                    <div className="sm:hidden">
                        <Image
                            src={mobileSrc}
                            alt={alt}
                            width={mobileWidth ?? width}
                            height={mobileHeight ?? height}
                            priority={priority}
                            sizes={mobileSizes}
                            className="block h-auto w-full"
                        />
                    </div>
                ) : null}
            </div>
        </figure>
    );
}

export { ProductFigure };
