import React from 'react';
import {AbsoluteFill, interpolate, useCurrentFrame} from 'remotion';
import {COLORS} from '../theme';

/** 深色科技感底：渐变 + 缓慢漂移的光晕 + 细网格。 */
export const Background: React.FC = () => {
  const frame = useCurrentFrame();
  const drift = (amp: number, period: number, phase: number) =>
    Math.sin((frame / period) * Math.PI * 2 + phase) * amp;

  return (
    <AbsoluteFill style={{backgroundColor: COLORS.bg}}>
      <AbsoluteFill
        style={{
          background:
            'radial-gradient(1200px 700px at 18% -10%, rgba(91,140,255,0.18), transparent 60%),' +
            'radial-gradient(1000px 700px at 92% 110%, rgba(55,214,166,0.13), transparent 60%),' +
            'radial-gradient(900px 600px at 70% 15%, rgba(167,139,250,0.10), transparent 65%)',
        }}
      />
      <AbsoluteFill
        style={{
          transform: `translate(${drift(30, 900, 0)}px, ${drift(18, 700, 1.2)}px)`,
          background:
            'radial-gradient(520px 520px at 22% 30%, rgba(91,140,255,0.16), transparent 70%),' +
            'radial-gradient(560px 560px at 82% 68%, rgba(55,214,166,0.10), transparent 70%)',
        }}
      />
      <AbsoluteFill
        style={{
          opacity: 0.5,
          backgroundImage:
            'linear-gradient(rgba(159,176,204,0.055) 1px, transparent 1px),' +
            'linear-gradient(90deg, rgba(159,176,204,0.055) 1px, transparent 1px)',
          backgroundSize: '64px 64px',
          maskImage:
            'radial-gradient(circle at 50% 40%, rgba(0,0,0,1), transparent 85%)',
          WebkitMaskImage:
            'radial-gradient(circle at 50% 40%, rgba(0,0,0,1), transparent 85%)',
        }}
      />
    </AbsoluteFill>
  );
};
