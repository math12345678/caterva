interface ParamSliderProps {
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  unit: string;
  onChange: (v: number) => void;
  color?: string;
  hint?: string;
  precision?: number; // decimal places; auto-detected if omitted
}

export default function ParamSlider({
  label, value, min, max, step, unit, onChange,
  color = '#1D8A72', hint, precision,
}: ParamSliderProps) {
  const pct = ((value - min) / (max - min)) * 100;

  const fmt = precision !== undefined
    ? value.toFixed(precision)
    : Number.isInteger(value) ? value : value.toFixed(1);

  return (
    <div className="space-y-1.5">
      <div className="flex items-center justify-between">
        <span className="text-[11px] text-white/40 font-mono">{label}</span>
        <span className="text-[13px] text-white/80 font-mono tabular-nums">
          {fmt}
          <span className="text-white/30 ml-0.5 text-[10px]">{unit}</span>
        </span>
      </div>
      {hint && (
        <span className="text-[9px] text-white/15 font-mono -mt-0.5 block">{hint}</span>
      )}
      <div className="relative">
        <input
          type="range"
          min={min}
          max={max}
          step={step}
          value={value}
          onChange={(e) => onChange(Number(e.target.value))}
          className="w-full h-1.5 rounded-full appearance-none bg-white/[0.06] cursor-pointer
            [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-4 [&::-webkit-slider-thumb]:h-4
            [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:border-2 [&::-webkit-slider-thumb]:border-white/20
            [&::-webkit-slider-thumb]:bg-[#0A0E0C] [&::-webkit-slider-thumb]:shadow-lg [&::-webkit-slider-thumb]:transition-all
            [&::-webkit-slider-thumb]:hover:scale-110 [&::-webkit-slider-thumb]:hover:border-[#1D8A72]/60
            [&::-moz-range-thumb]:w-4 [&::-moz-range-thumb]:h-4 [&::-moz-range-thumb]:rounded-full
            [&::-moz-range-thumb]:border-2 [&::-moz-range-thumb]:border-white/20 [&::-moz-range-thumb]:bg-[#0A0E0C]"
          aria-valuemin={min}
          aria-valuemax={max}
          aria-valuenow={value}
          aria-label={`${label} slider`}
          style={{
            background: `linear-gradient(to right, ${color}40 ${pct}%, rgba(255,255,255,0.06) ${pct}%)`,
          }}
        />
      </div>
    </div>
  );
}
