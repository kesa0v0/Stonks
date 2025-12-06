import { useEffect, useState } from 'react';
import { buildIdenticon } from '../utils/avatar';

interface AvatarProps {
  url?: string;
  seed?: string;
  size?: number;
  alt?: string;
  className?: string;
  borderClassName?: string;
}

export default function Avatar({ url, seed, size = 40, alt = 'avatar', className = '', borderClassName = '' }: AvatarProps) {
  const fallback = buildIdenticon(seed || 'anon');
  const [src, setSrc] = useState(url || fallback);

  useEffect(() => {
    setSrc(url || fallback);
  }, [url, fallback]);

  return (
    <img
      src={src}
      onError={() => setSrc(fallback)}
      alt={alt}
      className={`rounded-full object-cover ${className} ${borderClassName}`.trim()}
      style={{ width: size, height: size }}
    />
  );
}
