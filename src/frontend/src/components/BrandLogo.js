import React from 'react';

const LOGO_URL = `${process.env.PUBLIC_URL}/logo.png`;

/** Hawk logo from `public/logo.png` (transparent PNG). */
export default function BrandLogo({
  height = 32,
  className = '',
  alt = 'ReconHawx',
  ...rest
}) {
  return (
    <img
      src={LOGO_URL}
      alt={alt}
      height={height}
      className={`brand-logo ${className}`.trim()}
      {...rest}
    />
  );
}
