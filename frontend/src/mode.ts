export const isDemo=import.meta.env.VITE_DEMO==='true';
export const demoExplanation='Pages demonstration: authentic bundled SUMO recordings. New simulations, network conversion and calibration require the full local application.';
export const asset=(path:string)=>import.meta.env.BASE_URL+path.replace(/^\//,'');
