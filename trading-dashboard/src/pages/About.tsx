import React from 'react';
import { Cpu, Brain, Zap, Shield, TrendingUp, Users } from 'lucide-react';

export const About: React.FC = () => {

  const features = [
    {
      icon: Brain,
      title: 'AI-Powered Trading',
      description: 'Six specialized AI agents powered by Google Gemini models with unique trading strategies'
    },
    {
      icon: Zap,
      title: 'Real-Time Execution',
      description: 'Instant order placement and market connectivity with advanced risk management'
    },
    {
      icon: TrendingUp,
      title: 'Advanced Analytics',
      description: 'Comprehensive performance metrics, risk analysis, and market insights'
    },
    {
      icon: Shield,
      title: 'Enterprise Security',
      description: 'Military-grade security with encrypted communications and regulatory compliance'
    }
  ];

  const technologies = [
    'Python', 'Google Gemini AI', 'FastAPI', 'PostgreSQL', 'Redis', 'Docker', 'React', 'TypeScript'
  ];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="bg-gradient-to-r from-slate-900 to-slate-800 rounded-xl p-6 border border-slate-700">
        <h1 className="text-3xl font-bold text-white mb-2">About Sapphire AI</h1>
        <p className="text-slate-400">
          Advanced AI-powered cryptocurrency trading system with real-time market analysis and automated execution
        </p>
      </div>

      {/* Mission Statement */}
      <div className="bg-gradient-to-r from-blue-500/10 to-purple-500/10 rounded-xl p-6 border border-blue-500/20">
        <h2 className="text-xl font-semibold text-blue-400 mb-4">Our Mission</h2>
        <p className="text-slate-300 leading-relaxed">
          Sapphire AI revolutionizes cryptocurrency trading by combining cutting-edge artificial intelligence with
          sophisticated market analysis. Our platform empowers traders with automated, intelligent decision-making
          that operates 24/7, adapting to market conditions and executing trades with precision and discipline.
        </p>
      </div>

      {/* Key Features */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {features.map((feature, index) => (
          <div key={index} className="bg-slate-900/50 rounded-xl p-6 border border-slate-800">
            <div className="flex items-center gap-4 mb-4">
              <feature.icon className="h-8 w-8 text-blue-400" />
              <h3 className="text-lg font-semibold text-white">{feature.title}</h3>
            </div>
            <p className="text-slate-400 leading-relaxed">{feature.description}</p>
          </div>
        ))}
      </div>

      {/* Technology Stack */}
      <div className="bg-slate-900/50 rounded-xl p-6 border border-slate-800">
        <h2 className="text-xl font-semibold text-white mb-6">Technology Stack</h2>
        <div className="flex flex-wrap gap-3">
          {technologies.map((tech, index) => (
            <span key={index} className="bg-blue-500/20 text-blue-400 px-3 py-1 rounded-full text-sm font-medium">
              {tech}
            </span>
          ))}
        </div>
      </div>

      {/* Our Approach */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="bg-slate-900/50 rounded-xl p-6 border border-slate-800">
          <h2 className="text-xl font-semibold text-white mb-4">Our Approach</h2>
          <div className="space-y-4">
            <p className="text-slate-400 leading-relaxed">
              Sapphire AI combines quantitative analysis with artificial intelligence to create a trading system
              that learns, adapts, and evolves. Our multi-agent architecture ensures diverse perspectives and
              robust decision-making.
            </p>
            <p className="text-slate-400 leading-relaxed">
              We believe in transparency, security, and responsible AI development. Every trade is logged,
              every decision is auditable, and every risk is calculated with precision.
            </p>
          </div>
        </div>

        <div className="bg-slate-900/50 rounded-xl p-6 border border-slate-800">
          <h2 className="text-xl font-semibold text-white mb-4">System Architecture</h2>
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <Cpu className="h-5 w-5 text-blue-400" />
              <span className="text-slate-300">Docker containerized services</span>
            </div>
            <div className="flex items-center gap-3">
              <Users className="h-5 w-5 text-purple-400" />
              <span className="text-slate-300">6 specialized AI trading agents</span>
            </div>
            <div className="flex items-center gap-3">
              <Brain className="h-5 w-5 text-emerald-400" />
              <span className="text-slate-300">Google Gemini AI integration</span>
            </div>
            <div className="flex items-center gap-3">
              <Shield className="h-5 w-5 text-orange-400" />
              <span className="text-slate-300">Advanced risk management</span>
            </div>
          </div>
        </div>
      </div>

      {/* Disclaimer */}
      <div className="bg-amber-500/10 border border-amber-500/20 rounded-xl p-6">
        <h3 className="text-lg font-semibold text-amber-400 mb-3">⚠️ Important Disclaimer</h3>
        <p className="text-slate-400 leading-relaxed">
          Cryptocurrency trading involves significant risk and may not be suitable for all investors.
          Past performance does not guarantee future results. This system is for educational and
          informational purposes. Always conduct your own research and consider your risk tolerance
          before investing.
        </p>
      </div>
    </div>
  );
};

export default About;

