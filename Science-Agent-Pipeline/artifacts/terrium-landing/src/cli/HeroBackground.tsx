import { motion } from "framer-motion";

const blobs = [
  {
    size: 700,
    x: -15,
    y: -20,
    color: "rgba(29,138,114,0.10)",
    duration: 18,
    delay: 0,
  },
  {
    size: 500,
    x: 55,
    y: -5,
    color: "rgba(59,130,246,0.07)",
    duration: 22,
    delay: -5,
  },
  {
    size: 450,
    x: 25,
    y: 45,
    color: "rgba(245,158,11,0.04)",
    duration: 14,
    delay: -8,
  },
  {
    size: 300,
    x: 75,
    y: 55,
    color: "rgba(139,92,246,0.04)",
    duration: 20,
    delay: -3,
  },
  {
    size: 550,
    x: -5,
    y: 60,
    color: "rgba(29,138,114,0.06)",
    duration: 16,
    delay: -6,
  },
];

export default function HeroBackground() {
  return (
    <div
      className="absolute inset-0 overflow-hidden pointer-events-none"
      style={{ zIndex: 0 }}
    >
      {/* base gradient */}
      <div className="absolute inset-0 bg-gradient-to-b from-[#050807] via-[#050807] to-[#050807]" />

      {/* light wash from top */}
      <div
        className="absolute top-0 left-1/2 -translate-x-1/2 w-[1200px] h-[600px] opacity-[0.15]"
        style={{
          background:
            "radial-gradient(ellipse at 50% 0%, rgba(29,138,114,0.25) 0%, transparent 60%)",
        }}
      />

      {/* animated blobs */}
      {blobs.map((b, i) => (
        <motion.div
          key={i}
          className="absolute rounded-full"
          style={{
            width: b.size,
            height: b.size,
            background: `radial-gradient(circle at center, ${b.color}, transparent 70%)`,
            left: `${b.x}%`,
            top: `${b.y}%`,
            filter: "blur(80px)",
          }}
          animate={{
            x: [0, 40, -20, 30, 0],
            y: [0, -30, 20, -10, 0],
            scale: [1, 1.15, 0.9, 1.05, 1],
          }}
          transition={{
            duration: b.duration,
            delay: b.delay,
            repeat: Infinity,
            ease: "easeInOut",
          }}
        />
      ))}

      {/* subtle grid */}
      <div
        className="absolute inset-0 opacity-[0.15]"
        style={{
          backgroundImage:
            "linear-gradient(rgba(29,138,114,0.03) 1px, transparent 1px), linear-gradient(90deg, rgba(29,138,114,0.03) 1px, transparent 1px)",
          backgroundSize: "48px 48px",
        }}
      />
    </div>
  );
}
