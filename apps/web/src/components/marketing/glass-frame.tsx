import Image from "next/image";

import { cn } from "@/lib/utils";

type GlassFrameProps = {
    src: string;
    alt: string;
    className?: string;
    priority?: boolean;
    sizes?: string;
};

/**
 * A large product screenshot inside a glass bezel.
 *
 * The frame is deliberately light: a translucent white edge, a thin
 * specular highlight, and a soft inset shadow. It reads as glass over the
 * painterly hero background without tinting the screenshot itself.
 */
function GlassFrame({
    src,
    alt,
    className,
    priority = false,
    sizes = "(min-width: 1280px) 1120px, (min-width: 768px) 92vw, 100vw",
}: GlassFrameProps) {
    return (
        <figure className={cn("min-w-0", className)}>
            <div className="marketing-glass-frame">
                <div className="marketing-glass-screen">
                    <Image
                        src={src}
                        alt={alt}
                        width={3024}
                        height={1964}
                        priority={priority}
                        sizes={sizes}
                        className="block h-auto w-full"
                    />
                    <span
                        aria-hidden="true"
                        className="marketing-glass-sheen"
                    />
                </div>
            </div>
        </figure>
    );
}

export { GlassFrame };
