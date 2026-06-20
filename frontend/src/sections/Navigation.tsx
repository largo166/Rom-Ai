import { useState } from 'react';
import { NavLink } from 'react-router';
import { BookOpen, Bot, FolderKanban, Menu, Settings, Users, X } from 'lucide-react';

const navItems = [
  { label: '项目中心', href: '/projects', icon: FolderKanban },
  { label: '知识库', href: '/knowledge', icon: BookOpen },
  { label: 'AI代理', href: '/agents', icon: Bot },
  { label: '网络平台', href: '/network', icon: Users },
];

function navClass(isActive: boolean) {
  return [
    'flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors duration-200',
    isActive ? 'bg-amber-400/10 text-amber-300' : 'text-zinc-400 hover:bg-white/5 hover:text-white',
  ].join(' ');
}

export function Navigation() {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <nav className="fixed left-0 right-0 top-0 z-50 border-b border-[#333333]/50 bg-[#0A0A0A]/80 backdrop-blur-xl">
      <div className="mx-auto max-w-[1440px] px-6 md:px-12">
        <div className="flex h-16 items-center justify-between">
          <NavLink to="/projects" className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-amber-400 to-amber-600">
              <span className="text-sm font-bold text-black">R</span>
            </div>
            <span className="text-lg font-semibold tracking-tight text-white">ROM-AI</span>
          </NavLink>

          <div className="hidden items-center gap-1 md:flex">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink key={item.label} to={item.href} className={({ isActive }) => navClass(isActive)}>
                  <Icon size={16} />
                  {item.label}
                </NavLink>
              );
            })}
          </div>

          <div className="flex items-center gap-3">
            <NavLink
              to="/settings"
              className="hidden h-9 w-9 items-center justify-center rounded-lg text-zinc-400 transition-colors hover:bg-white/5 hover:text-white md:flex"
            >
              <Settings size={18} />
            </NavLink>
            <button className="text-white md:hidden" onClick={() => setMobileOpen(!mobileOpen)}>
              {mobileOpen ? <X size={24} /> : <Menu size={24} />}
            </button>
          </div>
        </div>

        {mobileOpen && (
          <div className="border-t border-[#333333]/50 py-4 md:hidden">
            {navItems.map((item) => {
              const Icon = item.icon;
              return (
                <NavLink
                  key={item.label}
                  to={item.href}
                  onClick={() => setMobileOpen(false)}
                  className={({ isActive }) => navClass(isActive)}
                >
                  <Icon size={18} />
                  {item.label}
                </NavLink>
              );
            })}
            <NavLink
              to="/settings"
              onClick={() => setMobileOpen(false)}
              className="mt-2 flex items-center gap-3 rounded-lg px-4 py-3 text-sm text-zinc-400 hover:text-white"
            >
              <Settings size={18} />
              设置
            </NavLink>
          </div>
        )}
      </div>
    </nav>
  );
}
