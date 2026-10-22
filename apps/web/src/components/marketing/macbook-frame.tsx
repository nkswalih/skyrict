import Image from "next/image";

import { cn } from "@/lib/utils";

type MacBookFrameProps = {
    src: string;
    alt: string;
    className?: string;
    priority?: boolean;
    sizes?: string;
};

function MacBookFrame({
    src,
    alt,
    className,
    priority = false,
    sizes = "(min-width: 1024px) 660px, (min-width: 768px) 80vw, 100vw",
}: MacBookFrameProps) {
    return (
        <div className={cn("marketing-device", className)}>
            <div className="marketing-device-lid">
                <div className="marketing-device-bezel">
                    <div className="marketing-device-screen">
                        <Image
                            src={src}
                            alt={alt}
                            fill
                            priority={priority}
                            sizes={sizes}
                            className="object-cover"
                        />
                        <span
                            aria-hidden="true"
                            className="marketing-device-glare"
                        />
                    </div>
                </div>
            </div>
            <div aria-hidden="true" className="marketing-device-base" />
        </div>
    );
}

export { MacBookFrame };
