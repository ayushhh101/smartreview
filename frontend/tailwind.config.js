export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: { sans: ['"IBM Plex Sans"', 'system-ui', 'sans-serif'] },
      colors: {
        ink: { DEFAULT: '#16202C', soft: '#4A5666', faint: '#7B8696' },
        rail: { DEFAULT: '#111A26', line: '#223042', text: '#A9B6C6' },
        paper: '#F3F4F6',
        pos: '#0F766E', neu: '#A16207', neg: '#B42318', brand: '#2B4C9B',
      },
    },
  },
}
