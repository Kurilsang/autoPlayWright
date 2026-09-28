import React from 'react';
import {COLORS} from '../theme';
import {Reveal} from './Reveal';

/** 纵向时间线：左侧轨道 + 节点逐条浮入。 */
export const RailTimeline: React.FC<{
  items: {tag: string; title: string; desc: string}[];
  startDelay?: number;
  stepDelay?: number;
}> = ({items, startDelay = 22, stepDelay = 46}) => {
  return (
    <div style={{position: 'relative', paddingLeft: 30}}>
      <div
        style={{
          position: 'absolute',
          left: 44,
          top: 18,
          bottom: 18,
          width: 3,
          borderRadius: 2,
          background:
            'linear-gradient(180deg, rgba(91,140,255,0.7), rgba(55,214,166,0.5))',
        }}
      />
      <div style={{display: 'flex', flexDirection: 'column', gap: 26}}>
        {items.map((item, i) => (
          <Reveal key={item.tag} delay={startDelay + i * stepDelay} y={24}>
            <div style={{display: 'flex', gap: 26, alignItems: 'flex-start'}}>
              <div
                style={{
                  width: 32,
                  height: 32,
                  borderRadius: 16,
                  marginTop: 8,
                  flexShrink: 0,
                  background: COLORS.bgSoft,
                  border: `3px solid ${i % 2 === 0 ? COLORS.accent : COLORS.accent2}`,
                  boxShadow: '0 0 18px rgba(91,140,255,0.35)',
                }}
              />
              <div style={{flex: 1}}>
                <div style={{display: 'flex', alignItems: 'center', gap: 14}}>
                  <span
                    style={{
                      fontSize: 19,
                      fontWeight: 800,
                      color: COLORS.accent2,
                      fontFamily: "'Cascadia Code', Consolas, monospace",
                      background: 'rgba(55,214,166,0.10)',
                      border: '1px solid rgba(55,214,166,0.35)',
                      borderRadius: 8,
                      padding: '3px 11px',
                    }}
                  >
                    {item.tag}
                  </span>
                  <span style={{fontSize: 28, fontWeight: 750, lineHeight: 1.35}}>
                    {item.title}
                  </span>
                </div>
                <div
                  style={{
                    marginTop: 8,
                    fontSize: 21,
                    lineHeight: 1.55,
                    color: COLORS.dim,
                    maxWidth: 1420,
                  }}
                >
                  {item.desc}
                </div>
              </div>
            </div>
          </Reveal>
        ))}
      </div>
    </div>
  );
};
