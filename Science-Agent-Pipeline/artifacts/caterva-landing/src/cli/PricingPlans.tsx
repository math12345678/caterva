import { motion } from "framer-motion";
import Reveal from "./Reveal";
import TerminalWindow from "./TerminalWindow";

const PLANS = [
  {
    name: "Free",
    price: "$0",
    period: "/month",
    desc: "For students and individual researchers exploring simulations.",
    features: [
      "Up to 10 simulations/month",
      "Browser-side RK4 solver",
      "CSV export",
      "Public simulation gallery",
      "Community support",
    ],
    cta: "Get Started",
    gradient: "from-signal/10 to-transparent",
    border: "hover:border-signal/25",
    featured: false,
  },
  {
    name: "Pilot",
    price: "Free",
    period: "during pilot",
    desc: "Early access for teaching labs and research groups. Full pipeline access.",
    features: [
      "Unlimited simulations",
      "Full pipeline (LLM + BRENDA + Caterva)",
      "SSE streaming results",
      "Literature provenance trail",
      "Priority support & onboarding",
      "Classroom dashboard (beta)",
    ],
    cta: "Join Waitlist",
    gradient: "from-caution/10 to-transparent",
    border: "hover:border-caution/30",
    featured: true,
    badge: "Recommended",
  },
  {
    name: "Institutional",
    price: "Coming",
    period: "soon",
    desc: "For universities and research institutes. Self-hosted or managed.",
    features: [
      "Everything in Pilot",
      "Self-hosted deployment",
      "SSO / SAML integration",
      "Admin dashboard & analytics",
      "Custom simulation domains",
      "Dedicated support SLA",
      "Batch simulation API",
    ],
    cta: "Contact Us",
    gradient: "from-muted/10 to-transparent",
    border: "hover:border-muted/25",
    featured: false,
  },
];

export default function PricingPlans() {
  return (
    <section
      className="max-w-3xl mx-auto px-4 md:px-6 py-10 section-bg-amber-strong scroll-mt-16"
      id="pricing"
    >
      <Reveal>
        <div className="flex items-center gap-4 mb-6">
          <span className="text-caution text-[11px] font-mono font-medium">
            PRICING
          </span>
          <span className="h-px flex-1 bg-gradient-to-r from-caution/20 to-transparent" />
        </div>
        <h2 className="section-header">Simple, transparent pricing</h2>
        <p className="font-sans text-[13px] text-fg/76 mb-8 -mt-2 max-w-sm">
          Start free. Upgrade when your lab needs more.
        </p>

        <TerminalWindow path="~ — caterva pricing --list" glow>
          <div className="mb-4 text-fg/92">
            <span className="text-signal">$</span> caterva pricing --list
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {PLANS.map((plan, i) => (
              <motion.div
                key={plan.name}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{
                  duration: 0.5,
                  delay: i * 0.1,
                  ease: [0.16, 1, 0.3, 1],
                }}
                className={`pricing-card ${plan.featured ? "featured" : ""} ${plan.border} relative`}
              >
                {plan.featured && plan.badge && (
                  <div className="pricing-badge">{plan.badge}</div>
                )}

                <div className="mb-4">
                  <h3 className="text-[14px] font-sans font-medium text-fg/85 mb-1">
                    {plan.name}
                  </h3>
                  <div className="flex items-baseline gap-1">
                    <span className="text-[28px] font-mono font-medium text-fg/92">
                      {plan.price}
                    </span>
                    <span className="text-[11px] text-fg/70">
                      {plan.period}
                    </span>
                  </div>
                  <p className="text-[11px] text-fg/76 mt-2 leading-relaxed">
                    {plan.desc}
                  </p>
                </div>

                <ul className="space-y-2 mb-6">
                  {plan.features.map((f) => (
                    <li
                      key={f}
                      className="flex items-start gap-2 text-[11px] text-fg/70"
                    >
                      <svg
                        className="w-3.5 h-3.5 mt-0.5 shrink-0 text-signal"
                        viewBox="0 0 14 14"
                        fill="none"
                      >
                        <path
                          d="M2.5 7.5L5.5 10.5L11.5 3.5"
                          stroke="currentColor"
                          strokeWidth="1.5"
                          strokeLinecap="round"
                          strokeLinejoin="round"
                        />
                      </svg>
                      {f}
                    </li>
                  ))}
                </ul>

                <a
                  href="#waitlist"
                  className={`block w-full text-center rounded-lg border py-2.5 text-[12px] font-medium transition-all duration-300 ${
                    plan.featured
                      ? "border-caution/30 bg-caution/[0.08] text-caution hover:bg-caution/[0.14]"
                      : "border-fg/[0.16] text-fg/70 hover:text-fg/78 hover:border-fg/[0.30] bg-fg/[0.02]"
                  }`}
                >
                  {plan.cta}
                </a>
              </motion.div>
            ))}
          </div>

          <p className="text-[10px] text-fg/66 mt-6 text-center leading-relaxed">
            All plans include full provenance tracing. No hidden fees. Cancel
            anytime.
            <br />
            <span className="text-fg/66">
              Educational discounts available —{" "}
            </span>
            <a
              href="mailto:admin.terrium@gmail.com"
              className="text-signal/60 hover:text-signal transition-colors"
            >
              contact us
            </a>
          </p>
        </TerminalWindow>
      </Reveal>
    </section>
  );
}
