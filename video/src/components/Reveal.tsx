import React from 'react';
import {Easing, interpolate, useCurrentFrame, useVideoConfig} from 'remotion';

/** 延迟淡入 + 上浮的小工具，delay 以帧计。 */
export const Reveal: React.FC<{
  delay: number;
  children: React.ReactNode;
  style?: React.CSSProperties;
  y?: number;
}> = ({delay, children, style, y = 26}) => {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const t = interpolate(frame, [delay, delay + fps * 0.45], [0, 1], {
    extrapolateLeft: 'clamp',
    extrapolateRight: 'clamp',
    easing: Easing.out(Easing.cubic),
  });
  return (
    <div
      style={{
        opacity: t,
        transform: `translateY(${(1 - t) * y}px)`,
        ...style,
      }}
    >
      {children}
    </div>
  );
};
