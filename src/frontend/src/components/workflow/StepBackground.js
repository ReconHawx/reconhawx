import React, { useState, useEffect } from 'react';
import { useReactFlow } from 'reactflow';

const StepBackground = ({ steps, canvasWidth }) => {
  const { getViewport } = useReactFlow();
  const [viewport, setViewport] = useState({ x: 0, y: 0, zoom: 1 });

  useEffect(() => {
    const updateViewport = () => {
      setViewport(getViewport());
    };
    
    updateViewport();
    
    const interval = setInterval(updateViewport, 100);
    return () => clearInterval(interval);
  }, [getViewport]);

  return (
    <div 
      style={{ 
        position: 'absolute', 
        top: 0, 
        left: 0, 
        width: '100%', 
        height: '100%', 
        pointerEvents: 'none',
        zIndex: 1,
        overflow: 'hidden'
      }}
    >
      <div
        style={{
          position: 'absolute',
          transform: `translate(${viewport.x}px, ${viewport.y}px) scale(${viewport.zoom})`,
          transformOrigin: '0 0',
          width: '100%',
          height: '100%'
        }}
      >
        {steps.map((step, index) => (
          <div
            key={step.id}
            className={`step-area-bg ${index % 2 === 0 ? 'step-bg-even' : 'step-bg-odd'}`}
            style={{
              position: 'absolute',
              left: -200,
              top: step.yPosition,
              width: (canvasWidth || '100%') + 400,
              height: step.height,
              borderRadius: '12px'
            }}
          >
            <div className="step-area-label">
              {step.name}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
};

export default StepBackground;