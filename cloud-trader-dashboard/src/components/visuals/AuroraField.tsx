import React from 'react';

type AuroraVariant = 'sapphire' | 'emerald' | 'amber';
type AuroraIntensity = 'soft' | 'bold' | 'medium';

interface AuroraFieldProps {
  className?: string;
  variant?: AuroraVariant;
  intensity?: AuroraIntensity;
}

const AuroraField: React.FC<AuroraFieldProps> = ({
  className = '',
  variant = 'sapphire',
  intensity = 'soft',
}) => {
  const variantClass = `aurora-variant-${variant}`;
  const intensityClass = `aurora-intensity-${intensity}`;

  return (
    <div
      className={`aurora-field ${variantClass} ${intensityClass} ${className}`.trim()}
      aria-hidden="true"
    >
      <span className="aurora-layer aurora-layer-primary" />
      <span className="aurora-layer aurora-layer-secondary" />
      <span className="aurora-noise" />
      <span className="aurora-grid" />
    </div>
  );
};

export default AuroraField;


