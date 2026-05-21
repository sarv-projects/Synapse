import React from 'react'
import { useInView } from '@/hooks/useInView'

type Direction = 'up' | 'down' | 'left' | 'right' | 'fade'

interface RevealProps {
  children: React.ReactNode
  direction?: Direction
  delay?: number   // ms
  className?: string
}

const directionMap: Record<Direction, string> = {
  up:    'translate-y-10 opacity-0',
  down:  '-translate-y-10 opacity-0',
  left:  'translate-x-10 opacity-0',
  right: '-translate-x-10 opacity-0',
  fade:  'opacity-0',
}

/**
 * Wraps children and animates them in when they scroll into view.
 * Usage: <Reveal direction="up" delay={100}><YourComponent /></Reveal>
 */
export function Reveal({ children, direction = 'up', delay = 0, className = '' }: RevealProps) {
  const { ref, inView } = useInView()

  return (
    <div
      ref={ref}
      className={`transition-all duration-700 ease-out ${
        inView ? 'translate-x-0 translate-y-0 opacity-100' : directionMap[direction]
      } ${className}`}
      style={{ transitionDelay: `${delay}ms` }}
    >
      {children}
    </div>
  )
}
