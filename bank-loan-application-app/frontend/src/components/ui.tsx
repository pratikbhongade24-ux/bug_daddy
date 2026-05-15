/**
 * Premium Fintech UI Components
 * Reusable, animated components for the loan application
 */

'use client'

import React from 'react'
import { motion, type HTMLMotionProps } from 'framer-motion'
import clsx from 'clsx'
import { shadows } from '../../lib/design-tokens'

// ============ BUTTON COMPONENT ============
interface ButtonProps extends Omit<HTMLMotionProps<'button'>, 'children'> {
  variant?: 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger'
  size?: 'sm' | 'md' | 'lg' | 'xl'
  isLoading?: boolean
  icon?: React.ReactNode
  fullWidth?: boolean
  children?: React.ReactNode
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', isLoading, icon, fullWidth, className, children, ...props }, ref) => {
    const baseStyles = clsx(
      'inline-flex min-w-0 items-center justify-center whitespace-normal text-center leading-tight font-medium transition-all duration-300',
      'rounded-xl shadow-sm',
      'disabled:opacity-50 disabled:cursor-not-allowed',
      'focus:outline-none focus:ring-2 focus:ring-offset-2',
      fullWidth && 'w-full'
    )

    const variants = {
      primary: clsx(
        'bg-gradient-to-r from-sky-500 to-blue-600',
        'text-white',
        'hover:shadow-lg hover:scale-105',
        'active:scale-95',
        'focus:ring-sky-500'
      ),
      secondary: clsx(
        'bg-gradient-to-r from-emerald-50 to-teal-50',
        'text-emerald-700',
        'border border-emerald-200',
        'hover:bg-gradient-to-r hover:from-emerald-100 hover:to-teal-100',
        'focus:ring-emerald-500'
      ),
      outline: clsx(
        'border-2 border-sky-500',
        'text-sky-600',
        'hover:bg-sky-50',
        'focus:ring-sky-500'
      ),
      ghost: clsx(
        'text-neutral-600',
        'hover:bg-neutral-100',
        'focus:ring-neutral-500'
      ),
      danger: clsx(
        'bg-gradient-to-r from-red-500 to-rose-600',
        'text-white',
        'hover:shadow-lg',
        'focus:ring-red-500'
      ),
    }

    const sizes = {
      sm: clsx('px-3 py-2 text-sm gap-2'),
      md: clsx('px-4 py-2.5 text-base gap-2'),
      lg: clsx('px-6 py-3 text-lg gap-3'),
      xl: clsx('px-8 py-4 text-lg gap-3'),
    }

    return (
      <motion.button
        ref={ref}
        whileHover={{ scale: isLoading ? 1 : 1.02 }}
        whileTap={{ scale: 0.98 }}
        className={clsx(baseStyles, variants[variant], sizes[size], className)}
        disabled={isLoading || props.disabled}
        {...props}
      >
        {isLoading && <span className="mr-2 shrink-0 animate-spin">⏳</span>}
        {icon && <span className="shrink-0">{icon}</span>}
        {children}
      </motion.button>
    )
  }
)
Button.displayName = 'Button'

// ============ CARD COMPONENT ============
interface CardProps extends Omit<HTMLMotionProps<'div'>, 'children'> {
  glass?: boolean
  hover?: boolean
  gradient?: boolean
  children?: React.ReactNode
}

export const Card = React.forwardRef<HTMLDivElement, CardProps>(
  ({ glass = false, hover = false, gradient = false, className, children, ...props }, ref) => (
    <motion.div
      ref={ref}
      whileHover={hover ? { y: -4, boxShadow: shadows.xl } : {}}
      className={clsx(
        'rounded-2xl p-6 transition-all duration-300',
        glass ? clsx(
          'backdrop-blur-md bg-white/80 border border-white/20',
          'shadow-lg'
        ) : clsx(
          'bg-white',
          'shadow-md'
        ),
        gradient && 'bg-gradient-to-br from-white to-gray-50/50',
        hover && 'cursor-pointer',
        className
      )}
      {...props}
    >
      {children}
    </motion.div>
  )
)
Card.displayName = 'Card'

// ============ BADGE COMPONENT ============
interface BadgeProps extends React.HTMLAttributes<HTMLSpanElement> {
  variant?: 'primary' | 'success' | 'warning' | 'error' | 'info' | 'neutral'
  size?: 'sm' | 'md' | 'lg'
}

export const Badge = React.forwardRef<HTMLSpanElement, BadgeProps>(
  ({ variant = 'info', size = 'md', className, children, ...props }, ref) => {
    const variants = {
      primary: 'bg-sky-100 text-sky-700 border border-sky-300',
      success: 'bg-emerald-100 text-emerald-700 border border-emerald-300',
      warning: 'bg-amber-100 text-amber-700 border border-amber-300',
      error: 'bg-red-100 text-red-700 border border-red-300',
      info: 'bg-sky-100 text-sky-700 border border-sky-300',
      neutral: 'bg-neutral-100 text-neutral-700 border border-neutral-300',
    }

    const sizes = {
      sm: 'px-2 py-1 text-xs',
      md: 'px-3 py-1.5 text-sm',
      lg: 'px-4 py-2 text-base',
    }

    return (
      <span
        ref={ref}
        className={clsx(
          'inline-flex items-center font-medium rounded-full',
          variants[variant],
          sizes[size],
          className
        )}
        {...props}
      >
        {children}
      </span>
    )
  }
)
Badge.displayName = 'Badge'

// ============ INPUT COMPONENT ============
interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  icon?: React.ReactNode
  floating?: boolean
}

export const Input = React.forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, icon, floating = false, className, style, ...props }, ref) => {
    const [isFocused, setIsFocused] = React.useState(false)
    const [hasValue, setHasValue] = React.useState(Boolean(props.value ?? props.defaultValue))
    const shouldHideFloatingIcon = floating && icon && (isFocused || hasValue)

    React.useEffect(() => {
      setHasValue(Boolean(props.value ?? props.defaultValue))
    }, [props.value, props.defaultValue])

    return (
      <motion.div className="w-full min-w-0">
        <div className="relative">
          {label && !floating && (
            <label className="block text-sm font-bold text-neutral-700 mb-2 leading-tight">
              {label}
            </label>
          )}
          
          <div className="relative">
            {icon && (
              <motion.div
                initial={false}
                animate={shouldHideFloatingIcon ? { opacity: 0, scale: 0.86, x: -4 } : { opacity: 1, scale: 1, x: 0 }}
                transition={{ duration: 0.16 }}
                className={clsx('pointer-events-none absolute left-4 z-10 shrink-0 text-neutral-400', floating ? 'top-[1.45rem]' : 'top-3.5')}
                aria-hidden="true"
              >
                {icon}
              </motion.div>
            )}
            
            {floating && label && (
              <motion.label
                initial={false}
                animate={isFocused || hasValue ? { opacity: 1 } : { opacity: 0.72 }}
                className={clsx(
                  'pointer-events-none absolute top-2 z-10 max-w-[calc(100%-2rem)] truncate text-[10px] font-extrabold uppercase tracking-[0.06em] text-neutral-500 origin-left leading-none',
                  icon && !shouldHideFloatingIcon ? 'left-12' : 'left-4'
                )}
                title={label}
              >
                {label}
              </motion.label>
            )}

            <input
              ref={ref}
              onFocus={() => setIsFocused(true)}
              onBlur={() => setIsFocused(false)}
              onChange={(e) => {
                setHasValue(Boolean(e.target.value))
                props.onChange?.(e)
              }}
              className={clsx(
                'w-full rounded-xl bg-white text-neutral-950',
                floating ? 'px-4' : 'px-4 py-3',
                'border-2 border-neutral-200',
                'focus:outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-500/20',
                'transition-all duration-200',
                'placeholder:text-neutral-400',
                error && 'border-red-500 focus:border-red-500 focus:ring-red-500/20',
                icon && !floating && 'pl-12',
                floating && 'loan-floating-input',
                className
              )}
              style={{
                ...style,
                ...(floating
                  ? {
                      minHeight: '3.75rem',
                      paddingLeft: icon && !shouldHideFloatingIcon ? '3rem' : '1rem',
                      paddingTop: '1.65rem',
                      paddingBottom: '0.55rem',
                      lineHeight: 1.2,
                    }
                  : {}),
              }}
              {...props}
            />
          </div>

          {error && (
            <motion.p
              initial={{ opacity: 0, y: -4 }}
              animate={{ opacity: 1, y: 0 }}
              className="mt-2 text-sm text-red-600"
            >
              {error}
            </motion.p>
          )}
        </div>
      </motion.div>
    )
  }
)
Input.displayName = 'Input'

// ============ LOADING SKELETON ============
export const Skeleton = ({ className }: { className?: string }) => (
  <motion.div
    className={clsx(
      'bg-gradient-to-r from-neutral-100 via-neutral-50 to-neutral-100',
      'rounded-xl',
      className
    )}
    animate={{ opacity: [0.5, 1, 0.5] }}
    transition={{ duration: 2, repeat: Infinity }}
  />
)

// ============ STAT CARD ============
interface StatCardProps {
  label: string
  value: string | number
  change?: string
  icon?: React.ReactNode
  trend?: 'up' | 'down' | 'neutral'
  className?: string
}

export const StatCard = ({ label, value, change, icon, trend = 'neutral', className }: StatCardProps) => {
  const trendColor = {
    up: 'text-emerald-600',
    down: 'text-red-600',
    neutral: 'text-neutral-600',
  }

  return (
    <Card hover glass className={clsx("cursor-default", className)}>
      <div className="flex items-start justify-between mb-4">
        <div>
          <p className="text-neutral-600 text-sm font-medium">{label}</p>
        </div>
        {icon && <div className="text-2xl opacity-50">{icon}</div>}
      </div>
      
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.1 }}
      >
        <p className="text-3xl font-bold text-neutral-900">{value}</p>
        {change && (
          <p className={clsx('text-sm font-medium mt-2', trendColor[trend])}>
            {change}
          </p>
        )}
      </motion.div>
    </Card>
  )
}

// ============ TIMELINE COMPONENT ============
interface TimelineItem {
  id: string
  label: string
  status: 'completed' | 'current' | 'pending'
  icon?: React.ReactNode
}

interface TimelineProps {
  items: TimelineItem[]
  orientation?: 'vertical' | 'horizontal'
}

export const Timeline = ({ items, orientation = 'vertical' }: TimelineProps) => {
  if (orientation === 'horizontal') {
    return (
      <div className="flex items-center justify-between">
        {items.map((item, idx) => (
          <div key={item.id} className="flex flex-col items-center flex-1">
            <motion.div
              initial={{ scale: 0 }}
              animate={{ scale: 1 }}
              className={clsx(
                'w-10 h-10 rounded-full flex items-center justify-center font-bold text-white',
                item.status === 'completed' && 'bg-emerald-500',
                item.status === 'current' && 'bg-sky-500 ring-4 ring-sky-200',
                item.status === 'pending' && 'bg-neutral-300'
              )}
            >
              {item.icon || (idx + 1)}
            </motion.div>
            <p className="text-sm font-medium text-neutral-700 mt-2 text-center">{item.label}</p>
            
            {idx < items.length - 1 && (
              <div className={clsx(
                'h-1 flex-1 mt-4',
                item.status === 'completed' ? 'bg-emerald-500' : 'bg-neutral-200'
              )} />
            )}
          </div>
        ))}
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {items.map((item, idx) => (
        <motion.div
          key={item.id}
          initial={{ opacity: 0, x: -20 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ delay: idx * 0.1 }}
          className="flex items-center gap-4"
        >
          <motion.div
            animate={item.status === 'current' ? { scale: [1, 1.2, 1] } : {}}
            transition={{ duration: 2, repeat: Infinity }}
            className={clsx(
              'w-10 h-10 rounded-full flex items-center justify-center font-bold text-white flex-shrink-0',
              item.status === 'completed' && 'bg-emerald-500',
              item.status === 'current' && 'bg-sky-500 ring-4 ring-sky-200',
              item.status === 'pending' && 'bg-neutral-300'
            )}
          >
            {item.icon || '✓'}
          </motion.div>
          
          <div>
            <p className="font-medium text-neutral-900">{item.label}</p>
            <p className="text-sm text-neutral-500 capitalize">{item.status}</p>
          </div>

          {idx < items.length - 1 && (
            <div className="absolute left-5 top-16 w-0.5 h-8 bg-neutral-200" />
          )}
        </motion.div>
      ))}
    </div>
  )
}

// ============ PROGRESS RING ============
interface ProgressRingProps {
  value: number
  max?: number
  size?: number
  color?: 'emerald' | 'sky' | 'amber'
  label?: string
}

export const ProgressRing = ({ value, max = 100, size = 120, color = 'sky', label }: ProgressRingProps) => {
  const radius = (size - 8) / 2
  const circumference = radius * 2 * Math.PI
  const percentage = (value / max) * 100
  const offset = circumference - (percentage / 100) * circumference

  const colors = {
    sky: '#0ea5e9',
    emerald: '#22c55e',
    amber: '#f59e0b',
  }

  return (
    <div className="flex flex-col items-center justify-center">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="transform -rotate-90">
          {/* Background circle */}
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke="#e4e4e7"
            strokeWidth="4"
          />
          
          {/* Progress circle */}
          <motion.circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={colors[color]}
            strokeWidth="4"
            strokeDasharray={circumference}
            initial={{ strokeDashoffset: circumference }}
            animate={{ strokeDashoffset: offset }}
            transition={{ duration: 0.8, ease: 'easeInOut' }}
            strokeLinecap="round"
          />
        </svg>

        {/* Center content */}
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-2xl font-bold text-neutral-900">{percentage.toFixed(0)}%</span>
          {label && <span className="text-xs text-neutral-600 mt-1">{label}</span>}
        </div>
      </div>
    </div>
  )
}
