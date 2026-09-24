var e=Object.create,t=Object.defineProperty,n=Object.getOwnPropertyDescriptor,r=Object.getOwnPropertyNames,i=Object.getPrototypeOf,a=Object.prototype.hasOwnProperty,o=(e,t)=>()=>(t||(e((t={exports:{}}).exports,t),e=null),t.exports),s=(e,i,o,s)=>{if(i&&typeof i==`object`||typeof i==`function`)for(var c=r(i),l=0,u=c.length,d;l<u;l++)d=c[l],!a.call(e,d)&&d!==o&&t(e,d,{get:(e=>i[e]).bind(null,d),enumerable:!(s=n(i,d))||s.enumerable});return e},c=(n,r,o)=>(o=n==null?{}:e(i(n)),s(r||!n||!n.__esModule||!a.call(n,`default`)?t(o,`default`,{value:n,enumerable:!0}):o,n));(function(){let e=document.createElement(`link`).relList;if(e&&e.supports&&e.supports(`modulepreload`))return;for(let e of document.querySelectorAll(`link[rel="modulepreload"]`))n(e);new MutationObserver(e=>{for(let t of e)if(t.type===`childList`)for(let e of t.addedNodes)e.tagName===`LINK`&&e.rel===`modulepreload`&&n(e)}).observe(document,{childList:!0,subtree:!0});function t(e){let t={};return e.integrity&&(t.integrity=e.integrity),e.referrerPolicy&&(t.referrerPolicy=e.referrerPolicy),t.credentials=e.crossOrigin===`use-credentials`?`include`:e.crossOrigin===`anonymous`?`omit`:`same-origin`,t}function n(e){if(e.ep)return;e.ep=!0;let n=t(e);fetch(e.href,n)}})();var l=o((e=>{var t=Symbol.for(`react.element`),n=Symbol.for(`react.portal`),r=Symbol.for(`react.fragment`),i=Symbol.for(`react.strict_mode`),a=Symbol.for(`react.profiler`),o=Symbol.for(`react.provider`),s=Symbol.for(`react.context`),c=Symbol.for(`react.forward_ref`),l=Symbol.for(`react.suspense`),u=Symbol.for(`react.memo`),d=Symbol.for(`react.lazy`),f=Symbol.iterator;function p(e){return typeof e!=`object`||!e?null:(e=f&&e[f]||e[`@@iterator`],typeof e==`function`?e:null)}var m={isMounted:function(){return!1},enqueueForceUpdate:function(){},enqueueReplaceState:function(){},enqueueSetState:function(){}},h=Object.assign,g={};function _(e,t,n){this.props=e,this.context=t,this.refs=g,this.updater=n||m}_.prototype.isReactComponent={},_.prototype.setState=function(e,t){if(typeof e!=`object`&&typeof e!=`function`&&e!=null)throw Error(`setState(...): takes an object of state variables to update or a function which returns an object of state variables.`);this.updater.enqueueSetState(this,e,t,`setState`)},_.prototype.forceUpdate=function(e){this.updater.enqueueForceUpdate(this,e,`forceUpdate`)};function v(){}v.prototype=_.prototype;function y(e,t,n){this.props=e,this.context=t,this.refs=g,this.updater=n||m}var b=y.prototype=new v;b.constructor=y,h(b,_.prototype),b.isPureReactComponent=!0;var x=Array.isArray,S=Object.prototype.hasOwnProperty,C={current:null},w={key:!0,ref:!0,__self:!0,__source:!0};function T(e,n,r){var i,a={},o=null,s=null;if(n!=null)for(i in n.ref!==void 0&&(s=n.ref),n.key!==void 0&&(o=``+n.key),n)S.call(n,i)&&!w.hasOwnProperty(i)&&(a[i]=n[i]);var c=arguments.length-2;if(c===1)a.children=r;else if(1<c){for(var l=Array(c),u=0;u<c;u++)l[u]=arguments[u+2];a.children=l}if(e&&e.defaultProps)for(i in c=e.defaultProps,c)a[i]===void 0&&(a[i]=c[i]);return{$$typeof:t,type:e,key:o,ref:s,props:a,_owner:C.current}}function E(e,n){return{$$typeof:t,type:e.type,key:n,ref:e.ref,props:e.props,_owner:e._owner}}function D(e){return typeof e==`object`&&!!e&&e.$$typeof===t}function O(e){var t={"=":`=0`,":":`=2`};return`$`+e.replace(/[=:]/g,function(e){return t[e]})}var k=/\/+/g;function A(e,t){return typeof e==`object`&&e&&e.key!=null?O(``+e.key):t.toString(36)}function j(e,r,i,a,o){var s=typeof e;(s===`undefined`||s===`boolean`)&&(e=null);var c=!1;if(e===null)c=!0;else switch(s){case`string`:case`number`:c=!0;break;case`object`:switch(e.$$typeof){case t:case n:c=!0}}if(c)return c=e,o=o(c),e=a===``?`.`+A(c,0):a,x(o)?(i=``,e!=null&&(i=e.replace(k,`$&/`)+`/`),j(o,r,i,``,function(e){return e})):o!=null&&(D(o)&&(o=E(o,i+(!o.key||c&&c.key===o.key?``:(``+o.key).replace(k,`$&/`)+`/`)+e)),r.push(o)),1;if(c=0,a=a===``?`.`:a+`:`,x(e))for(var l=0;l<e.length;l++){s=e[l];var u=a+A(s,l);c+=j(s,r,i,u,o)}else if(u=p(e),typeof u==`function`)for(e=u.call(e),l=0;!(s=e.next()).done;)s=s.value,u=a+A(s,l++),c+=j(s,r,i,u,o);else if(s===`object`)throw r=String(e),Error(`Objects are not valid as a React child (found: `+(r===`[object Object]`?`object with keys {`+Object.keys(e).join(`, `)+`}`:r)+`). If you meant to render a collection of children, use an array instead.`);return c}function M(e,t,n){if(e==null)return e;var r=[],i=0;return j(e,r,``,``,function(e){return t.call(n,e,i++)}),r}function N(e){if(e._status===-1){var t=e._result;t=t(),t.then(function(t){(e._status===0||e._status===-1)&&(e._status=1,e._result=t)},function(t){(e._status===0||e._status===-1)&&(e._status=2,e._result=t)}),e._status===-1&&(e._status=0,e._result=t)}if(e._status===1)return e._result.default;throw e._result}var P={current:null},F={transition:null},ee={ReactCurrentDispatcher:P,ReactCurrentBatchConfig:F,ReactCurrentOwner:C};function te(){throw Error(`act(...) is not supported in production builds of React.`)}e.Children={map:M,forEach:function(e,t,n){M(e,function(){t.apply(this,arguments)},n)},count:function(e){var t=0;return M(e,function(){t++}),t},toArray:function(e){return M(e,function(e){return e})||[]},only:function(e){if(!D(e))throw Error(`React.Children.only expected to receive a single React element child.`);return e}},e.Component=_,e.Fragment=r,e.Profiler=a,e.PureComponent=y,e.StrictMode=i,e.Suspense=l,e.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED=ee,e.act=te,e.cloneElement=function(e,n,r){if(e==null)throw Error(`React.cloneElement(...): The argument must be a React element, but you passed `+e+`.`);var i=h({},e.props),a=e.key,o=e.ref,s=e._owner;if(n!=null){if(n.ref!==void 0&&(o=n.ref,s=C.current),n.key!==void 0&&(a=``+n.key),e.type&&e.type.defaultProps)var c=e.type.defaultProps;for(l in n)S.call(n,l)&&!w.hasOwnProperty(l)&&(i[l]=n[l]===void 0&&c!==void 0?c[l]:n[l])}var l=arguments.length-2;if(l===1)i.children=r;else if(1<l){c=Array(l);for(var u=0;u<l;u++)c[u]=arguments[u+2];i.children=c}return{$$typeof:t,type:e.type,key:a,ref:o,props:i,_owner:s}},e.createContext=function(e){return e={$$typeof:s,_currentValue:e,_currentValue2:e,_threadCount:0,Provider:null,Consumer:null,_defaultValue:null,_globalName:null},e.Provider={$$typeof:o,_context:e},e.Consumer=e},e.createElement=T,e.createFactory=function(e){var t=T.bind(null,e);return t.type=e,t},e.createRef=function(){return{current:null}},e.forwardRef=function(e){return{$$typeof:c,render:e}},e.isValidElement=D,e.lazy=function(e){return{$$typeof:d,_payload:{_status:-1,_result:e},_init:N}},e.memo=function(e,t){return{$$typeof:u,type:e,compare:t===void 0?null:t}},e.startTransition=function(e){var t=F.transition;F.transition={};try{e()}finally{F.transition=t}},e.unstable_act=te,e.useCallback=function(e,t){return P.current.useCallback(e,t)},e.useContext=function(e){return P.current.useContext(e)},e.useDebugValue=function(){},e.useDeferredValue=function(e){return P.current.useDeferredValue(e)},e.useEffect=function(e,t){return P.current.useEffect(e,t)},e.useId=function(){return P.current.useId()},e.useImperativeHandle=function(e,t,n){return P.current.useImperativeHandle(e,t,n)},e.useInsertionEffect=function(e,t){return P.current.useInsertionEffect(e,t)},e.useLayoutEffect=function(e,t){return P.current.useLayoutEffect(e,t)},e.useMemo=function(e,t){return P.current.useMemo(e,t)},e.useReducer=function(e,t,n){return P.current.useReducer(e,t,n)},e.useRef=function(e){return P.current.useRef(e)},e.useState=function(e){return P.current.useState(e)},e.useSyncExternalStore=function(e,t,n){return P.current.useSyncExternalStore(e,t,n)},e.useTransition=function(){return P.current.useTransition()},e.version=`18.3.1`})),u=o(((e,t)=>{t.exports=l()})),d=o((e=>{function t(e,t){var n=e.length;e.push(t);a:for(;0<n;){var r=n-1>>>1,a=e[r];if(0<i(a,t))e[r]=t,e[n]=a,n=r;else break a}}function n(e){return e.length===0?null:e[0]}function r(e){if(e.length===0)return null;var t=e[0],n=e.pop();if(n!==t){e[0]=n;a:for(var r=0,a=e.length,o=a>>>1;r<o;){var s=2*(r+1)-1,c=e[s],l=s+1,u=e[l];if(0>i(c,n))l<a&&0>i(u,c)?(e[r]=u,e[l]=n,r=l):(e[r]=c,e[s]=n,r=s);else if(l<a&&0>i(u,n))e[r]=u,e[l]=n,r=l;else break a}}return t}function i(e,t){var n=e.sortIndex-t.sortIndex;return n===0?e.id-t.id:n}if(typeof performance==`object`&&typeof performance.now==`function`){var a=performance;e.unstable_now=function(){return a.now()}}else{var o=Date,s=o.now();e.unstable_now=function(){return o.now()-s}}var c=[],l=[],u=1,d=null,f=3,p=!1,m=!1,h=!1,g=typeof setTimeout==`function`?setTimeout:null,_=typeof clearTimeout==`function`?clearTimeout:null,v=typeof setImmediate<`u`?setImmediate:null;typeof navigator<`u`&&navigator.scheduling!==void 0&&navigator.scheduling.isInputPending!==void 0&&navigator.scheduling.isInputPending.bind(navigator.scheduling);function y(e){for(var i=n(l);i!==null;){if(i.callback===null)r(l);else if(i.startTime<=e)r(l),i.sortIndex=i.expirationTime,t(c,i);else break;i=n(l)}}function b(e){if(h=!1,y(e),!m){if(n(c)!==null)m=!0,M(x);else{var t=n(l);t!==null&&N(b,t.startTime-e)}}}function x(t,i){m=!1,h&&(h=!1,_(w),w=-1),p=!0;var a=f;try{for(y(i),d=n(c);d!==null&&(!(d.expirationTime>i)||t&&!D());){var o=d.callback;if(typeof o==`function`){d.callback=null,f=d.priorityLevel;var s=o(d.expirationTime<=i);i=e.unstable_now(),typeof s==`function`?d.callback=s:d===n(c)&&r(c),y(i)}else r(c);d=n(c)}if(d!==null)var u=!0;else{var g=n(l);g!==null&&N(b,g.startTime-i),u=!1}return u}finally{d=null,f=a,p=!1}}var S=!1,C=null,w=-1,T=5,E=-1;function D(){return!(e.unstable_now()-E<T)}function O(){if(C!==null){var t=e.unstable_now();E=t;var n=!0;try{n=C(!0,t)}finally{n?k():(S=!1,C=null)}}else S=!1}var k;if(typeof v==`function`)k=function(){v(O)};else if(typeof MessageChannel<`u`){var A=new MessageChannel,j=A.port2;A.port1.onmessage=O,k=function(){j.postMessage(null)}}else k=function(){g(O,0)};function M(e){C=e,S||(S=!0,k())}function N(t,n){w=g(function(){t(e.unstable_now())},n)}e.unstable_IdlePriority=5,e.unstable_ImmediatePriority=1,e.unstable_LowPriority=4,e.unstable_NormalPriority=3,e.unstable_Profiling=null,e.unstable_UserBlockingPriority=2,e.unstable_cancelCallback=function(e){e.callback=null},e.unstable_continueExecution=function(){m||p||(m=!0,M(x))},e.unstable_forceFrameRate=function(e){0>e||125<e?console.error(`forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported`):T=0<e?Math.floor(1e3/e):5},e.unstable_getCurrentPriorityLevel=function(){return f},e.unstable_getFirstCallbackNode=function(){return n(c)},e.unstable_next=function(e){switch(f){case 1:case 2:case 3:var t=3;break;default:t=f}var n=f;f=t;try{return e()}finally{f=n}},e.unstable_pauseExecution=function(){},e.unstable_requestPaint=function(){},e.unstable_runWithPriority=function(e,t){switch(e){case 1:case 2:case 3:case 4:case 5:break;default:e=3}var n=f;f=e;try{return t()}finally{f=n}},e.unstable_scheduleCallback=function(r,i,a){var o=e.unstable_now();switch(typeof a==`object`&&a?(a=a.delay,a=typeof a==`number`&&0<a?o+a:o):a=o,r){case 1:var s=-1;break;case 2:s=250;break;case 5:s=1073741823;break;case 4:s=1e4;break;default:s=5e3}return s=a+s,r={id:u++,callback:i,priorityLevel:r,startTime:a,expirationTime:s,sortIndex:-1},a>o?(r.sortIndex=a,t(l,r),n(c)===null&&r===n(l)&&(h?(_(w),w=-1):h=!0,N(b,a-o))):(r.sortIndex=s,t(c,r),m||p||(m=!0,M(x))),r},e.unstable_shouldYield=D,e.unstable_wrapCallback=function(e){var t=f;return function(){var n=f;f=t;try{return e.apply(this,arguments)}finally{f=n}}}})),f=o(((e,t)=>{t.exports=d()})),p=o((e=>{var t=u(),n=f();function r(e){for(var t=`https://reactjs.org/docs/error-decoder.html?invariant=`+e,n=1;n<arguments.length;n++)t+=`&args[]=`+encodeURIComponent(arguments[n]);return`Minified React error #`+e+`; visit `+t+` for the full message or use the non-minified dev environment for full errors and additional helpful warnings.`}var i=new Set,a={};function o(e,t){s(e,t),s(e+`Capture`,t)}function s(e,t){for(a[e]=t,e=0;e<t.length;e++)i.add(t[e])}var c=typeof window<`u`&&window.document!==void 0&&window.document.createElement!==void 0,l=Object.prototype.hasOwnProperty,d=/^[:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD][:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\-.0-9\u00B7\u0300-\u036F\u203F-\u2040]*$/,p={},m={};function h(e){return l.call(m,e)?!0:l.call(p,e)?!1:d.test(e)?m[e]=!0:(p[e]=!0,!1)}function g(e,t,n,r){if(n!==null&&n.type===0)return!1;switch(typeof t){case`function`:case`symbol`:return!0;case`boolean`:return r?!1:n===null?(e=e.toLowerCase().slice(0,5),e!==`data-`&&e!==`aria-`):!n.acceptsBooleans;default:return!1}}function _(e,t,n,r){if(t==null||g(e,t,n,r))return!0;if(r)return!1;if(n!==null)switch(n.type){case 3:return!t;case 4:return!1===t;case 5:return isNaN(t);case 6:return isNaN(t)||1>t}return!1}function v(e,t,n,r,i,a,o){this.acceptsBooleans=t===2||t===3||t===4,this.attributeName=r,this.attributeNamespace=i,this.mustUseProperty=n,this.propertyName=e,this.type=t,this.sanitizeURL=a,this.removeEmptyString=o}var y={};`children dangerouslySetInnerHTML defaultValue defaultChecked innerHTML suppressContentEditableWarning suppressHydrationWarning style`.split(` `).forEach(function(e){y[e]=new v(e,0,!1,e,null,!1,!1)}),[[`acceptCharset`,`accept-charset`],[`className`,`class`],[`htmlFor`,`for`],[`httpEquiv`,`http-equiv`]].forEach(function(e){var t=e[0];y[t]=new v(t,1,!1,e[1],null,!1,!1)}),[`contentEditable`,`draggable`,`spellCheck`,`value`].forEach(function(e){y[e]=new v(e,2,!1,e.toLowerCase(),null,!1,!1)}),[`autoReverse`,`externalResourcesRequired`,`focusable`,`preserveAlpha`].forEach(function(e){y[e]=new v(e,2,!1,e,null,!1,!1)}),`allowFullScreen async autoFocus autoPlay controls default defer disabled disablePictureInPicture disableRemotePlayback formNoValidate hidden loop noModule noValidate open playsInline readOnly required reversed scoped seamless itemScope`.split(` `).forEach(function(e){y[e]=new v(e,3,!1,e.toLowerCase(),null,!1,!1)}),[`checked`,`multiple`,`muted`,`selected`].forEach(function(e){y[e]=new v(e,3,!0,e,null,!1,!1)}),[`capture`,`download`].forEach(function(e){y[e]=new v(e,4,!1,e,null,!1,!1)}),[`cols`,`rows`,`size`,`span`].forEach(function(e){y[e]=new v(e,6,!1,e,null,!1,!1)}),[`rowSpan`,`start`].forEach(function(e){y[e]=new v(e,5,!1,e.toLowerCase(),null,!1,!1)});var b=/[\-:]([a-z])/g;function x(e){return e[1].toUpperCase()}`accent-height alignment-baseline arabic-form baseline-shift cap-height clip-path clip-rule color-interpolation color-interpolation-filters color-profile color-rendering dominant-baseline enable-background fill-opacity fill-rule flood-color flood-opacity font-family font-size font-size-adjust font-stretch font-style font-variant font-weight glyph-name glyph-orientation-horizontal glyph-orientation-vertical horiz-adv-x horiz-origin-x image-rendering letter-spacing lighting-color marker-end marker-mid marker-start overline-position overline-thickness paint-order panose-1 pointer-events rendering-intent shape-rendering stop-color stop-opacity strikethrough-position strikethrough-thickness stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity stroke-width text-anchor text-decoration text-rendering underline-position underline-thickness unicode-bidi unicode-range units-per-em v-alphabetic v-hanging v-ideographic v-mathematical vector-effect vert-adv-y vert-origin-x vert-origin-y word-spacing writing-mode xmlns:xlink x-height`.split(` `).forEach(function(e){var t=e.replace(b,x);y[t]=new v(t,1,!1,e,null,!1,!1)}),`xlink:actuate xlink:arcrole xlink:role xlink:show xlink:title xlink:type`.split(` `).forEach(function(e){var t=e.replace(b,x);y[t]=new v(t,1,!1,e,`http://www.w3.org/1999/xlink`,!1,!1)}),[`xml:base`,`xml:lang`,`xml:space`].forEach(function(e){var t=e.replace(b,x);y[t]=new v(t,1,!1,e,`http://www.w3.org/XML/1998/namespace`,!1,!1)}),[`tabIndex`,`crossOrigin`].forEach(function(e){y[e]=new v(e,1,!1,e.toLowerCase(),null,!1,!1)}),y.xlinkHref=new v(`xlinkHref`,1,!1,`xlink:href`,`http://www.w3.org/1999/xlink`,!0,!1),[`src`,`href`,`action`,`formAction`].forEach(function(e){y[e]=new v(e,1,!1,e.toLowerCase(),null,!0,!0)});function S(e,t,n,r){var i=y.hasOwnProperty(t)?y[t]:null;(i===null?r||!(2<t.length)||t[0]!==`o`&&t[0]!==`O`||t[1]!==`n`&&t[1]!==`N`:i.type!==0)&&(_(t,n,i,r)&&(n=null),r||i===null?h(t)&&(n===null?e.removeAttribute(t):e.setAttribute(t,``+n)):i.mustUseProperty?e[i.propertyName]=n===null?i.type!==3&&``:n:(t=i.attributeName,r=i.attributeNamespace,n===null?e.removeAttribute(t):(i=i.type,n=i===3||i===4&&!0===n?``:``+n,r?e.setAttributeNS(r,t,n):e.setAttribute(t,n))))}var C=t.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED,w=Symbol.for(`react.element`),T=Symbol.for(`react.portal`),E=Symbol.for(`react.fragment`),D=Symbol.for(`react.strict_mode`),O=Symbol.for(`react.profiler`),k=Symbol.for(`react.provider`),A=Symbol.for(`react.context`),j=Symbol.for(`react.forward_ref`),M=Symbol.for(`react.suspense`),N=Symbol.for(`react.suspense_list`),P=Symbol.for(`react.memo`),F=Symbol.for(`react.lazy`),ee=Symbol.for(`react.offscreen`),te=Symbol.iterator;function I(e){return typeof e!=`object`||!e?null:(e=te&&e[te]||e[`@@iterator`],typeof e==`function`?e:null)}var L=Object.assign,ne;function re(e){if(ne===void 0)try{throw Error()}catch(e){var t=e.stack.trim().match(/\n( *(at )?)/);ne=t&&t[1]||``}return`
`+ne+e}var ie=!1;function ae(e,t){if(!e||ie)return``;ie=!0;var n=Error.prepareStackTrace;Error.prepareStackTrace=void 0;try{if(t){if(t=function(){throw Error()},Object.defineProperty(t.prototype,"props",{set:function(){throw Error()}}),typeof Reflect==`object`&&Reflect.construct){try{Reflect.construct(t,[])}catch(e){var r=e}Reflect.construct(e,[],t)}else{try{t.call()}catch(e){r=e}e.call(t.prototype)}}else{try{throw Error()}catch(e){r=e}e()}}catch(t){if(t&&r&&typeof t.stack==`string`){for(var i=t.stack.split(`
`),a=r.stack.split(`
`),o=i.length-1,s=a.length-1;1<=o&&0<=s&&i[o]!==a[s];)s--;for(;1<=o&&0<=s;o--,s--)if(i[o]!==a[s]){if(o!==1||s!==1)do if(o--,s--,0>s||i[o]!==a[s]){var c=`
`+i[o].replace(` at new `,` at `);return e.displayName&&c.includes(`<anonymous>`)&&(c=c.replace(`<anonymous>`,e.displayName)),c}while(1<=o&&0<=s);break}}}finally{ie=!1,Error.prepareStackTrace=n}return(e=e?e.displayName||e.name:``)?re(e):``}function oe(e){switch(e.tag){case 5:return re(e.type);case 16:return re(`Lazy`);case 13:return re(`Suspense`);case 19:return re(`SuspenseList`);case 0:case 2:case 15:return e=ae(e.type,!1),e;case 11:return e=ae(e.type.render,!1),e;case 1:return e=ae(e.type,!0),e;default:return``}}function se(e){if(e==null)return null;if(typeof e==`function`)return e.displayName||e.name||null;if(typeof e==`string`)return e;switch(e){case E:return`Fragment`;case T:return`Portal`;case O:return`Profiler`;case D:return`StrictMode`;case M:return`Suspense`;case N:return`SuspenseList`}if(typeof e==`object`)switch(e.$$typeof){case A:return(e.displayName||`Context`)+`.Consumer`;case k:return(e._context.displayName||`Context`)+`.Provider`;case j:var t=e.render;return e=e.displayName,e||=(e=t.displayName||t.name||``,e===``?`ForwardRef`:`ForwardRef(`+e+`)`),e;case P:return t=e.displayName||null,t===null?se(e.type)||`Memo`:t;case F:t=e._payload,e=e._init;try{return se(e(t))}catch{}}return null}function ce(e){var t=e.type;switch(e.tag){case 24:return`Cache`;case 9:return(t.displayName||`Context`)+`.Consumer`;case 10:return(t._context.displayName||`Context`)+`.Provider`;case 18:return`DehydratedFragment`;case 11:return e=t.render,e=e.displayName||e.name||``,t.displayName||(e===``?`ForwardRef`:`ForwardRef(`+e+`)`);case 7:return`Fragment`;case 5:return t;case 4:return`Portal`;case 3:return`Root`;case 6:return`Text`;case 16:return se(t);case 8:return t===D?`StrictMode`:`Mode`;case 22:return`Offscreen`;case 12:return`Profiler`;case 21:return`Scope`;case 13:return`Suspense`;case 19:return`SuspenseList`;case 25:return`TracingMarker`;case 1:case 0:case 17:case 2:case 14:case 15:if(typeof t==`function`)return t.displayName||t.name||null;if(typeof t==`string`)return t}return null}function le(e){switch(typeof e){case`boolean`:case`number`:case`string`:case`undefined`:return e;case`object`:return e;default:return``}}function ue(e){var t=e.type;return(e=e.nodeName)&&e.toLowerCase()===`input`&&(t===`checkbox`||t===`radio`)}function de(e){var t=ue(e)?`checked`:`value`,n=Object.getOwnPropertyDescriptor(e.constructor.prototype,t),r=``+e[t];if(!e.hasOwnProperty(t)&&n!==void 0&&typeof n.get==`function`&&typeof n.set==`function`){var i=n.get,a=n.set;return Object.defineProperty(e,t,{configurable:!0,get:function(){return i.call(this)},set:function(e){r=``+e,a.call(this,e)}}),Object.defineProperty(e,t,{enumerable:n.enumerable}),{getValue:function(){return r},setValue:function(e){r=``+e},stopTracking:function(){e._valueTracker=null,delete e[t]}}}}function fe(e){e._valueTracker||=de(e)}function pe(e){if(!e)return!1;var t=e._valueTracker;if(!t)return!0;var n=t.getValue(),r=``;return e&&(r=ue(e)?e.checked?`true`:`false`:e.value),e=r,e!==n&&(t.setValue(e),!0)}function me(e){if(e||=typeof document<`u`?document:void 0,e===void 0)return null;try{return e.activeElement||e.body}catch{return e.body}}function he(e,t){var n=t.checked;return L({},t,{defaultChecked:void 0,defaultValue:void 0,value:void 0,checked:n??e._wrapperState.initialChecked})}function ge(e,t){var n=t.defaultValue==null?``:t.defaultValue,r=t.checked==null?t.defaultChecked:t.checked;n=le(t.value==null?n:t.value),e._wrapperState={initialChecked:r,initialValue:n,controlled:t.type===`checkbox`||t.type===`radio`?t.checked!=null:t.value!=null}}function _e(e,t){t=t.checked,t!=null&&S(e,`checked`,t,!1)}function ve(e,t){_e(e,t);var n=le(t.value),r=t.type;if(n!=null)r===`number`?(n===0&&e.value===``||e.value!=n)&&(e.value=``+n):e.value!==``+n&&(e.value=``+n);else if(r===`submit`||r===`reset`){e.removeAttribute(`value`);return}t.hasOwnProperty(`value`)?R(e,t.type,n):t.hasOwnProperty(`defaultValue`)&&R(e,t.type,le(t.defaultValue)),t.checked==null&&t.defaultChecked!=null&&(e.defaultChecked=!!t.defaultChecked)}function ye(e,t,n){if(t.hasOwnProperty(`value`)||t.hasOwnProperty(`defaultValue`)){var r=t.type;if(!(r!==`submit`&&r!==`reset`||t.value!==void 0&&t.value!==null))return;t=``+e._wrapperState.initialValue,n||t===e.value||(e.value=t),e.defaultValue=t}n=e.name,n!==``&&(e.name=``),e.defaultChecked=!!e._wrapperState.initialChecked,n!==``&&(e.name=n)}function R(e,t,n){(t!==`number`||me(e.ownerDocument)!==e)&&(n==null?e.defaultValue=``+e._wrapperState.initialValue:e.defaultValue!==``+n&&(e.defaultValue=``+n))}var be=Array.isArray;function xe(e,t,n,r){if(e=e.options,t){t={};for(var i=0;i<n.length;i++)t[`$`+n[i]]=!0;for(n=0;n<e.length;n++)i=t.hasOwnProperty(`$`+e[n].value),e[n].selected!==i&&(e[n].selected=i),i&&r&&(e[n].defaultSelected=!0)}else{for(n=``+le(n),t=null,i=0;i<e.length;i++){if(e[i].value===n){e[i].selected=!0,r&&(e[i].defaultSelected=!0);return}t!==null||e[i].disabled||(t=e[i])}t!==null&&(t.selected=!0)}}function Se(e,t){if(t.dangerouslySetInnerHTML!=null)throw Error(r(91));return L({},t,{value:void 0,defaultValue:void 0,children:``+e._wrapperState.initialValue})}function z(e,t){var n=t.value;if(n==null){if(n=t.children,t=t.defaultValue,n!=null){if(t!=null)throw Error(r(92));if(be(n)){if(1<n.length)throw Error(r(93));n=n[0]}t=n}t??=``,n=t}e._wrapperState={initialValue:le(n)}}function Ce(e,t){var n=le(t.value),r=le(t.defaultValue);n!=null&&(n=``+n,n!==e.value&&(e.value=n),t.defaultValue==null&&e.defaultValue!==n&&(e.defaultValue=n)),r!=null&&(e.defaultValue=``+r)}function B(e){var t=e.textContent;t===e._wrapperState.initialValue&&t!==``&&t!==null&&(e.value=t)}function V(e){switch(e){case`svg`:return`http://www.w3.org/2000/svg`;case`math`:return`http://www.w3.org/1998/Math/MathML`;default:return`http://www.w3.org/1999/xhtml`}}function we(e,t){return e==null||e===`http://www.w3.org/1999/xhtml`?V(t):e===`http://www.w3.org/2000/svg`&&t===`foreignObject`?`http://www.w3.org/1999/xhtml`:e}var Te,Ee=function(e){return typeof MSApp<`u`&&MSApp.execUnsafeLocalFunction?function(t,n,r,i){MSApp.execUnsafeLocalFunction(function(){return e(t,n,r,i)})}:e}(function(e,t){if(e.namespaceURI!==`http://www.w3.org/2000/svg`||`innerHTML`in e)e.innerHTML=t;else{for(Te||=document.createElement(`div`),Te.innerHTML=`<svg>`+t.valueOf().toString()+`</svg>`,t=Te.firstChild;e.firstChild;)e.removeChild(e.firstChild);for(;t.firstChild;)e.appendChild(t.firstChild)}});function De(e,t){if(t){var n=e.firstChild;if(n&&n===e.lastChild&&n.nodeType===3){n.nodeValue=t;return}}e.textContent=t}var Oe={animationIterationCount:!0,aspectRatio:!0,borderImageOutset:!0,borderImageSlice:!0,borderImageWidth:!0,boxFlex:!0,boxFlexGroup:!0,boxOrdinalGroup:!0,columnCount:!0,columns:!0,flex:!0,flexGrow:!0,flexPositive:!0,flexShrink:!0,flexNegative:!0,flexOrder:!0,gridArea:!0,gridRow:!0,gridRowEnd:!0,gridRowSpan:!0,gridRowStart:!0,gridColumn:!0,gridColumnEnd:!0,gridColumnSpan:!0,gridColumnStart:!0,fontWeight:!0,lineClamp:!0,lineHeight:!0,opacity:!0,order:!0,orphans:!0,tabSize:!0,widows:!0,zIndex:!0,zoom:!0,fillOpacity:!0,floodOpacity:!0,stopOpacity:!0,strokeDasharray:!0,strokeDashoffset:!0,strokeMiterlimit:!0,strokeOpacity:!0,strokeWidth:!0},ke=[`Webkit`,`ms`,`Moz`,`O`];Object.keys(Oe).forEach(function(e){ke.forEach(function(t){t=t+e.charAt(0).toUpperCase()+e.substring(1),Oe[t]=Oe[e]})});function Ae(e,t,n){return t==null||typeof t==`boolean`||t===``?``:n||typeof t!=`number`||t===0||Oe.hasOwnProperty(e)&&Oe[e]?(``+t).trim():t+`px`}function je(e,t){for(var n in e=e.style,t)if(t.hasOwnProperty(n)){var r=n.indexOf(`--`)===0,i=Ae(n,t[n],r);n===`float`&&(n=`cssFloat`),r?e.setProperty(n,i):e[n]=i}}var Me=L({menuitem:!0},{area:!0,base:!0,br:!0,col:!0,embed:!0,hr:!0,img:!0,input:!0,keygen:!0,link:!0,meta:!0,param:!0,source:!0,track:!0,wbr:!0});function Ne(e,t){if(t){if(Me[e]&&(t.children!=null||t.dangerouslySetInnerHTML!=null))throw Error(r(137,e));if(t.dangerouslySetInnerHTML!=null){if(t.children!=null)throw Error(r(60));if(typeof t.dangerouslySetInnerHTML!=`object`||!(`__html`in t.dangerouslySetInnerHTML))throw Error(r(61))}if(t.style!=null&&typeof t.style!=`object`)throw Error(r(62))}}function Pe(e,t){if(e.indexOf(`-`)===-1)return typeof t.is==`string`;switch(e){case`annotation-xml`:case`color-profile`:case`font-face`:case`font-face-src`:case`font-face-uri`:case`font-face-format`:case`font-face-name`:case`missing-glyph`:return!1;default:return!0}}var Fe=null;function Ie(e){return e=e.target||e.srcElement||window,e.correspondingUseElement&&(e=e.correspondingUseElement),e.nodeType===3?e.parentNode:e}var Le=null,Re=null,ze=null;function Be(e){if(e=Li(e)){if(typeof Le!=`function`)throw Error(r(280));var t=e.stateNode;t&&(t=zi(t),Le(e.stateNode,e.type,t))}}function Ve(e){Re?ze?ze.push(e):ze=[e]:Re=e}function He(){if(Re){var e=Re,t=ze;if(ze=Re=null,Be(e),t)for(e=0;e<t.length;e++)Be(t[e])}}function Ue(e,t){return e(t)}function We(){}var Ge=!1;function Ke(e,t,n){if(Ge)return e(t,n);Ge=!0;try{return Ue(e,t,n)}finally{Ge=!1,(Re!==null||ze!==null)&&(We(),He())}}function qe(e,t){var n=e.stateNode;if(n===null)return null;var i=zi(n);if(i===null)return null;n=i[t];a:switch(t){case`onClick`:case`onClickCapture`:case`onDoubleClick`:case`onDoubleClickCapture`:case`onMouseDown`:case`onMouseDownCapture`:case`onMouseMove`:case`onMouseMoveCapture`:case`onMouseUp`:case`onMouseUpCapture`:case`onMouseEnter`:(i=!i.disabled)||(e=e.type,i=e!==`button`&&e!==`input`&&e!==`select`&&e!==`textarea`),e=!i;break a;default:e=!1}if(e)return null;if(n&&typeof n!=`function`)throw Error(r(231,t,typeof n));return n}var Je=!1;if(c)try{var Ye={};Object.defineProperty(Ye,"passive",{get:function(){Je=!0}}),window.addEventListener(`test`,Ye,Ye),window.removeEventListener(`test`,Ye,Ye)}catch{Je=!1}function Xe(e,t,n,r,i,a,o,s,c){var l=Array.prototype.slice.call(arguments,3);try{t.apply(n,l)}catch(e){this.onError(e)}}var Ze=!1,Qe=null,$e=!1,et=null,tt={onError:function(e){Ze=!0,Qe=e}};function nt(e,t,n,r,i,a,o,s,c){Ze=!1,Qe=null,Xe.apply(tt,arguments)}function rt(e,t,n,i,a,o,s,c,l){if(nt.apply(this,arguments),Ze){if(Ze){var u=Qe;Ze=!1,Qe=null}else throw Error(r(198));$e||($e=!0,et=u)}}function it(e){var t=e,n=e;if(e.alternate)for(;t.return;)t=t.return;else{e=t;do t=e,t.flags&4098&&(n=t.return),e=t.return;while(e)}return t.tag===3?n:null}function at(e){if(e.tag===13){var t=e.memoizedState;if(t===null&&(e=e.alternate,e!==null&&(t=e.memoizedState)),t!==null)return t.dehydrated}return null}function ot(e){if(it(e)!==e)throw Error(r(188))}function st(e){var t=e.alternate;if(!t){if(t=it(e),t===null)throw Error(r(188));return t===e?e:null}for(var n=e,i=t;;){var a=n.return;if(a===null)break;var o=a.alternate;if(o===null){if(i=a.return,i!==null){n=i;continue}break}if(a.child===o.child){for(o=a.child;o;){if(o===n)return ot(a),e;if(o===i)return ot(a),t;o=o.sibling}throw Error(r(188))}if(n.return!==i.return)n=a,i=o;else{for(var s=!1,c=a.child;c;){if(c===n){s=!0,n=a,i=o;break}if(c===i){s=!0,i=a,n=o;break}c=c.sibling}if(!s){for(c=o.child;c;){if(c===n){s=!0,n=o,i=a;break}if(c===i){s=!0,i=o,n=a;break}c=c.sibling}if(!s)throw Error(r(189))}}if(n.alternate!==i)throw Error(r(190))}if(n.tag!==3)throw Error(r(188));return n.stateNode.current===n?e:t}function ct(e){return e=st(e),e===null?null:lt(e)}function lt(e){if(e.tag===5||e.tag===6)return e;for(e=e.child;e!==null;){var t=lt(e);if(t!==null)return t;e=e.sibling}return null}var ut=n.unstable_scheduleCallback,dt=n.unstable_cancelCallback,ft=n.unstable_shouldYield,pt=n.unstable_requestPaint,mt=n.unstable_now,ht=n.unstable_getCurrentPriorityLevel,gt=n.unstable_ImmediatePriority,_t=n.unstable_UserBlockingPriority,vt=n.unstable_NormalPriority,yt=n.unstable_LowPriority,bt=n.unstable_IdlePriority,xt=null,St=null;function Ct(e){if(St&&typeof St.onCommitFiberRoot==`function`)try{St.onCommitFiberRoot(xt,e,void 0,(e.current.flags&128)==128)}catch{}}var wt=Math.clz32?Math.clz32:Dt,Tt=Math.log,Et=Math.LN2;function Dt(e){return e>>>=0,e===0?32:31-(Tt(e)/Et|0)|0}var Ot=64,kt=4194304;function At(e){switch(e&-e){case 1:return 1;case 2:return 2;case 4:return 4;case 8:return 8;case 16:return 16;case 32:return 32;case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:return e&4194240;case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:return e&130023424;case 134217728:return 134217728;case 268435456:return 268435456;case 536870912:return 536870912;case 1073741824:return 1073741824;default:return e}}function H(e,t){var n=e.pendingLanes;if(n===0)return 0;var r=0,i=e.suspendedLanes,a=e.pingedLanes,o=n&268435455;if(o!==0){var s=o&~i;s===0?(a&=o,a!==0&&(r=At(a))):r=At(s)}else o=n&~i,o===0?a!==0&&(r=At(a)):r=At(o);if(r===0)return 0;if(t!==0&&t!==r&&(t&i)===0&&(i=r&-r,a=t&-t,i>=a||i===16&&a&4194240))return t;if(r&4&&(r|=n&16),t=e.entangledLanes,t!==0)for(e=e.entanglements,t&=r;0<t;)n=31-wt(t),i=1<<n,r|=e[n],t&=~i;return r}function jt(e,t){switch(e){case 1:case 2:case 4:return t+250;case 8:case 16:case 32:case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:return t+5e3;case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:return-1;case 134217728:case 268435456:case 536870912:case 1073741824:return-1;default:return-1}}function Mt(e,t){for(var n=e.suspendedLanes,r=e.pingedLanes,i=e.expirationTimes,a=e.pendingLanes;0<a;){var o=31-wt(a),s=1<<o,c=i[o];c===-1?((s&n)===0||(s&r)!==0)&&(i[o]=jt(s,t)):c<=t&&(e.expiredLanes|=s),a&=~s}}function Nt(e){return e=e.pendingLanes&-1073741825,e===0?e&1073741824?1073741824:0:e}function Pt(){var e=Ot;return Ot<<=1,!(Ot&4194240)&&(Ot=64),e}function Ft(e){for(var t=[],n=0;31>n;n++)t.push(e);return t}function It(e,t,n){e.pendingLanes|=t,t!==536870912&&(e.suspendedLanes=0,e.pingedLanes=0),e=e.eventTimes,t=31-wt(t),e[t]=n}function Lt(e,t){var n=e.pendingLanes&~t;e.pendingLanes=t,e.suspendedLanes=0,e.pingedLanes=0,e.expiredLanes&=t,e.mutableReadLanes&=t,e.entangledLanes&=t,t=e.entanglements;var r=e.eventTimes;for(e=e.expirationTimes;0<n;){var i=31-wt(n),a=1<<i;t[i]=0,r[i]=-1,e[i]=-1,n&=~a}}function Rt(e,t){var n=e.entangledLanes|=t;for(e=e.entanglements;n;){var r=31-wt(n),i=1<<r;i&t|e[r]&t&&(e[r]|=t),n&=~i}}var zt=0;function Bt(e){return e&=-e,1<e?4<e?e&268435455?16:536870912:4:1}var Vt,Ht,Ut,Wt,Gt,Kt=!1,qt=[],Jt=null,Yt=null,Xt=null,Zt=new Map,Qt=new Map,$t=[],en=`mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset submit`.split(` `);function tn(e,t){switch(e){case`focusin`:case`focusout`:Jt=null;break;case`dragenter`:case`dragleave`:Yt=null;break;case`mouseover`:case`mouseout`:Xt=null;break;case`pointerover`:case`pointerout`:Zt.delete(t.pointerId);break;case`gotpointercapture`:case`lostpointercapture`:Qt.delete(t.pointerId)}}function nn(e,t,n,r,i,a){return e===null||e.nativeEvent!==a?(e={blockedOn:t,domEventName:n,eventSystemFlags:r,nativeEvent:a,targetContainers:[i]},t!==null&&(t=Li(t),t!==null&&Ht(t)),e):(e.eventSystemFlags|=r,t=e.targetContainers,i!==null&&t.indexOf(i)===-1&&t.push(i),e)}function rn(e,t,n,r,i){switch(t){case`focusin`:return Jt=nn(Jt,e,t,n,r,i),!0;case`dragenter`:return Yt=nn(Yt,e,t,n,r,i),!0;case`mouseover`:return Xt=nn(Xt,e,t,n,r,i),!0;case`pointerover`:var a=i.pointerId;return Zt.set(a,nn(Zt.get(a)||null,e,t,n,r,i)),!0;case`gotpointercapture`:return a=i.pointerId,Qt.set(a,nn(Qt.get(a)||null,e,t,n,r,i)),!0}return!1}function an(e){var t=Ii(e.target);if(t!==null){var n=it(t);if(n!==null){if(t=n.tag,t===13){if(t=at(n),t!==null){e.blockedOn=t,Gt(e.priority,function(){Ut(n)});return}}else if(t===3&&n.stateNode.current.memoizedState.isDehydrated){e.blockedOn=n.tag===3?n.stateNode.containerInfo:null;return}}}e.blockedOn=null}function on(e){if(e.blockedOn!==null)return!1;for(var t=e.targetContainers;0<t.length;){var n=_n(e.domEventName,e.eventSystemFlags,t[0],e.nativeEvent);if(n===null){n=e.nativeEvent;var r=new n.constructor(n.type,n);Fe=r,n.target.dispatchEvent(r),Fe=null}else return t=Li(n),t!==null&&Ht(t),e.blockedOn=n,!1;t.shift()}return!0}function sn(e,t,n){on(e)&&n.delete(t)}function cn(){Kt=!1,Jt!==null&&on(Jt)&&(Jt=null),Yt!==null&&on(Yt)&&(Yt=null),Xt!==null&&on(Xt)&&(Xt=null),Zt.forEach(sn),Qt.forEach(sn)}function ln(e,t){e.blockedOn===t&&(e.blockedOn=null,Kt||(Kt=!0,n.unstable_scheduleCallback(n.unstable_NormalPriority,cn)))}function un(e){function t(t){return ln(t,e)}if(0<qt.length){ln(qt[0],e);for(var n=1;n<qt.length;n++){var r=qt[n];r.blockedOn===e&&(r.blockedOn=null)}}for(Jt!==null&&ln(Jt,e),Yt!==null&&ln(Yt,e),Xt!==null&&ln(Xt,e),Zt.forEach(t),Qt.forEach(t),n=0;n<$t.length;n++)r=$t[n],r.blockedOn===e&&(r.blockedOn=null);for(;0<$t.length&&(n=$t[0],n.blockedOn===null);)an(n),n.blockedOn===null&&$t.shift()}var dn=C.ReactCurrentBatchConfig,fn=!0;function pn(e,t,n,r){var i=zt,a=dn.transition;dn.transition=null;try{zt=1,hn(e,t,n,r)}finally{zt=i,dn.transition=a}}function mn(e,t,n,r){var i=zt,a=dn.transition;dn.transition=null;try{zt=4,hn(e,t,n,r)}finally{zt=i,dn.transition=a}}function hn(e,t,n,r){if(fn){var i=_n(e,t,n,r);if(i===null)ci(e,t,r,gn,n),tn(e,r);else if(rn(i,e,t,n,r))r.stopPropagation();else if(tn(e,r),t&4&&-1<en.indexOf(e)){for(;i!==null;){var a=Li(i);if(a!==null&&Vt(a),a=_n(e,t,n,r),a===null&&ci(e,t,r,gn,n),a===i)break;i=a}i!==null&&r.stopPropagation()}else ci(e,t,r,null,n)}}var gn=null;function _n(e,t,n,r){if(gn=null,e=Ie(r),e=Ii(e),e!==null){if(t=it(e),t===null)e=null;else if(n=t.tag,n===13){if(e=at(t),e!==null)return e;e=null}else if(n===3){if(t.stateNode.current.memoizedState.isDehydrated)return t.tag===3?t.stateNode.containerInfo:null;e=null}else t!==e&&(e=null)}return gn=e,null}function vn(e){switch(e){case`cancel`:case`click`:case`close`:case`contextmenu`:case`copy`:case`cut`:case`auxclick`:case`dblclick`:case`dragend`:case`dragstart`:case`drop`:case`focusin`:case`focusout`:case`input`:case`invalid`:case`keydown`:case`keypress`:case`keyup`:case`mousedown`:case`mouseup`:case`paste`:case`pause`:case`play`:case`pointercancel`:case`pointerdown`:case`pointerup`:case`ratechange`:case`reset`:case`resize`:case`seeked`:case`submit`:case`touchcancel`:case`touchend`:case`touchstart`:case`volumechange`:case`change`:case`selectionchange`:case`textInput`:case`compositionstart`:case`compositionend`:case`compositionupdate`:case`beforeblur`:case`afterblur`:case`beforeinput`:case`blur`:case`fullscreenchange`:case`focus`:case`hashchange`:case`popstate`:case`select`:case`selectstart`:return 1;case`drag`:case`dragenter`:case`dragexit`:case`dragleave`:case`dragover`:case`mousemove`:case`mouseout`:case`mouseover`:case`pointermove`:case`pointerout`:case`pointerover`:case`scroll`:case`toggle`:case`touchmove`:case`wheel`:case`mouseenter`:case`mouseleave`:case`pointerenter`:case`pointerleave`:return 4;case`message`:switch(ht()){case gt:return 1;case _t:return 4;case vt:case yt:return 16;case bt:return 536870912;default:return 16}default:return 16}}var yn=null,bn=null,xn=null;function Sn(){if(xn)return xn;var e,t=bn,n=t.length,r,i=`value`in yn?yn.value:yn.textContent,a=i.length;for(e=0;e<n&&t[e]===i[e];e++);var o=n-e;for(r=1;r<=o&&t[n-r]===i[a-r];r++);return xn=i.slice(e,1<r?1-r:void 0)}function Cn(e){var t=e.keyCode;return`charCode`in e?(e=e.charCode,e===0&&t===13&&(e=13)):e=t,e===10&&(e=13),32<=e||e===13?e:0}function wn(){return!0}function Tn(){return!1}function En(e){function t(t,n,r,i,a){for(var o in this._reactName=t,this._targetInst=r,this.type=n,this.nativeEvent=i,this.target=a,this.currentTarget=null,e)e.hasOwnProperty(o)&&(t=e[o],this[o]=t?t(i):i[o]);return this.isDefaultPrevented=(i.defaultPrevented==null?!1===i.returnValue:i.defaultPrevented)?wn:Tn,this.isPropagationStopped=Tn,this}return L(t.prototype,{preventDefault:function(){this.defaultPrevented=!0;var e=this.nativeEvent;e&&(e.preventDefault?e.preventDefault():typeof e.returnValue!=`unknown`&&(e.returnValue=!1),this.isDefaultPrevented=wn)},stopPropagation:function(){var e=this.nativeEvent;e&&(e.stopPropagation?e.stopPropagation():typeof e.cancelBubble!=`unknown`&&(e.cancelBubble=!0),this.isPropagationStopped=wn)},persist:function(){},isPersistent:wn}),t}var Dn={eventPhase:0,bubbles:0,cancelable:0,timeStamp:function(e){return e.timeStamp||Date.now()},defaultPrevented:0,isTrusted:0},On=En(Dn),kn=L({},Dn,{view:0,detail:0}),An=En(kn),jn,Mn,Nn,Pn=L({},kn,{screenX:0,screenY:0,clientX:0,clientY:0,pageX:0,pageY:0,ctrlKey:0,shiftKey:0,altKey:0,metaKey:0,getModifierState:Gn,button:0,buttons:0,relatedTarget:function(e){return e.relatedTarget===void 0?e.fromElement===e.srcElement?e.toElement:e.fromElement:e.relatedTarget},movementX:function(e){return`movementX`in e?e.movementX:(e!==Nn&&(Nn&&e.type===`mousemove`?(jn=e.screenX-Nn.screenX,Mn=e.screenY-Nn.screenY):Mn=jn=0,Nn=e),jn)},movementY:function(e){return`movementY`in e?e.movementY:Mn}}),Fn=En(Pn),In=En(L({},Pn,{dataTransfer:0})),Ln=En(L({},kn,{relatedTarget:0})),Rn=En(L({},Dn,{animationName:0,elapsedTime:0,pseudoElement:0})),zn=En(L({},Dn,{clipboardData:function(e){return`clipboardData`in e?e.clipboardData:window.clipboardData}})),Bn=En(L({},Dn,{data:0})),Vn={Esc:`Escape`,Spacebar:` `,Left:`ArrowLeft`,Up:`ArrowUp`,Right:`ArrowRight`,Down:`ArrowDown`,Del:`Delete`,Win:`OS`,Menu:`ContextMenu`,Apps:`ContextMenu`,Scroll:`ScrollLock`,MozPrintableKey:`Unidentified`},Hn={8:`Backspace`,9:`Tab`,12:`Clear`,13:`Enter`,16:`Shift`,17:`Control`,18:`Alt`,19:`Pause`,20:`CapsLock`,27:`Escape`,32:` `,33:`PageUp`,34:`PageDown`,35:`End`,36:`Home`,37:`ArrowLeft`,38:`ArrowUp`,39:`ArrowRight`,40:`ArrowDown`,45:`Insert`,46:`Delete`,112:`F1`,113:`F2`,114:`F3`,115:`F4`,116:`F5`,117:`F6`,118:`F7`,119:`F8`,120:`F9`,121:`F10`,122:`F11`,123:`F12`,144:`NumLock`,145:`ScrollLock`,224:`Meta`},Un={Alt:`altKey`,Control:`ctrlKey`,Meta:`metaKey`,Shift:`shiftKey`};function Wn(e){var t=this.nativeEvent;return t.getModifierState?t.getModifierState(e):(e=Un[e])?!!t[e]:!1}function Gn(){return Wn}var Kn=En(L({},kn,{key:function(e){if(e.key){var t=Vn[e.key]||e.key;if(t!==`Unidentified`)return t}return e.type===`keypress`?(e=Cn(e),e===13?`Enter`:String.fromCharCode(e)):e.type===`keydown`||e.type===`keyup`?Hn[e.keyCode]||`Unidentified`:``},code:0,location:0,ctrlKey:0,shiftKey:0,altKey:0,metaKey:0,repeat:0,locale:0,getModifierState:Gn,charCode:function(e){return e.type===`keypress`?Cn(e):0},keyCode:function(e){return e.type===`keydown`||e.type===`keyup`?e.keyCode:0},which:function(e){return e.type===`keypress`?Cn(e):e.type===`keydown`||e.type===`keyup`?e.keyCode:0}})),U=En(L({},Pn,{pointerId:0,width:0,height:0,pressure:0,tangentialPressure:0,tiltX:0,tiltY:0,twist:0,pointerType:0,isPrimary:0})),qn=En(L({},kn,{touches:0,targetTouches:0,changedTouches:0,altKey:0,metaKey:0,ctrlKey:0,shiftKey:0,getModifierState:Gn})),Jn=En(L({},Dn,{propertyName:0,elapsedTime:0,pseudoElement:0})),Yn=En(L({},Pn,{deltaX:function(e){return`deltaX`in e?e.deltaX:`wheelDeltaX`in e?-e.wheelDeltaX:0},deltaY:function(e){return`deltaY`in e?e.deltaY:`wheelDeltaY`in e?-e.wheelDeltaY:`wheelDelta`in e?-e.wheelDelta:0},deltaZ:0,deltaMode:0})),W=[9,13,27,32],Xn=c&&`CompositionEvent`in window,Zn=null;c&&`documentMode`in document&&(Zn=document.documentMode);var Qn=c&&`TextEvent`in window&&!Zn,$n=c&&(!Xn||Zn&&8<Zn&&11>=Zn),er=` `,G=!1;function tr(e,t){switch(e){case`keyup`:return W.indexOf(t.keyCode)!==-1;case`keydown`:return t.keyCode!==229;case`keypress`:case`mousedown`:case`focusout`:return!0;default:return!1}}function nr(e){return e=e.detail,typeof e==`object`&&`data`in e?e.data:null}var rr=!1;function ir(e,t){switch(e){case`compositionend`:return nr(t);case`keypress`:return t.which===32?(G=!0,er):null;case`textInput`:return e=t.data,e===er&&G?null:e;default:return null}}function ar(e,t){if(rr)return e===`compositionend`||!Xn&&tr(e,t)?(e=Sn(),xn=bn=yn=null,rr=!1,e):null;switch(e){case`paste`:return null;case`keypress`:if(!(t.ctrlKey||t.altKey||t.metaKey)||t.ctrlKey&&t.altKey){if(t.char&&1<t.char.length)return t.char;if(t.which)return String.fromCharCode(t.which)}return null;case`compositionend`:return $n&&t.locale!==`ko`?null:t.data;default:return null}}var or={color:!0,date:!0,datetime:!0,"datetime-local":!0,email:!0,month:!0,number:!0,password:!0,range:!0,search:!0,tel:!0,text:!0,time:!0,url:!0,week:!0};function sr(e){var t=e&&e.nodeName&&e.nodeName.toLowerCase();return t===`input`?!!or[e.type]:t===`textarea`}function cr(e,t,n,r){Ve(r),t=ui(t,`onChange`),0<t.length&&(n=new On(`onChange`,`change`,null,n,r),e.push({event:n,listeners:t}))}var lr=null,ur=null;function dr(e){ni(e,0)}function fr(e){if(pe(Ri(e)))return e}function pr(e,t){if(e===`change`)return t}var mr=!1;if(c){var hr;if(c){var gr=`oninput`in document;if(!gr){var _r=document.createElement(`div`);_r.setAttribute(`oninput`,`return;`),gr=typeof _r.oninput==`function`}hr=gr}else hr=!1;mr=hr&&(!document.documentMode||9<document.documentMode)}function vr(){lr&&(lr.detachEvent(`onpropertychange`,yr),ur=lr=null)}function yr(e){if(e.propertyName===`value`&&fr(ur)){var t=[];cr(t,ur,e,Ie(e)),Ke(dr,t)}}function br(e,t,n){e===`focusin`?(vr(),lr=t,ur=n,lr.attachEvent(`onpropertychange`,yr)):e===`focusout`&&vr()}function xr(e){if(e===`selectionchange`||e===`keyup`||e===`keydown`)return fr(ur)}function Sr(e,t){if(e===`click`)return fr(t)}function Cr(e,t){if(e===`input`||e===`change`)return fr(t)}function wr(e,t){return e===t&&(e!==0||1/e==1/t)||e!==e&&t!==t}var Tr=typeof Object.is==`function`?Object.is:wr;function Er(e,t){if(Tr(e,t))return!0;if(typeof e!=`object`||!e||typeof t!=`object`||!t)return!1;var n=Object.keys(e),r=Object.keys(t);if(n.length!==r.length)return!1;for(r=0;r<n.length;r++){var i=n[r];if(!l.call(t,i)||!Tr(e[i],t[i]))return!1}return!0}function Dr(e){for(;e&&e.firstChild;)e=e.firstChild;return e}function Or(e,t){var n=Dr(e);e=0;for(var r;n;){if(n.nodeType===3){if(r=e+n.textContent.length,e<=t&&r>=t)return{node:n,offset:t-e};e=r}a:{for(;n;){if(n.nextSibling){n=n.nextSibling;break a}n=n.parentNode}n=void 0}n=Dr(n)}}function kr(e,t){return e&&t?e===t?!0:e&&e.nodeType===3?!1:t&&t.nodeType===3?kr(e,t.parentNode):`contains`in e?e.contains(t):e.compareDocumentPosition?!!(e.compareDocumentPosition(t)&16):!1:!1}function Ar(){for(var e=window,t=me();t instanceof e.HTMLIFrameElement;){try{var n=typeof t.contentWindow.location.href==`string`}catch{n=!1}if(n)e=t.contentWindow;else break;t=me(e.document)}return t}function jr(e){var t=e&&e.nodeName&&e.nodeName.toLowerCase();return t&&(t===`input`&&(e.type===`text`||e.type===`search`||e.type===`tel`||e.type===`url`||e.type===`password`)||t===`textarea`||e.contentEditable===`true`)}function Mr(e){var t=Ar(),n=e.focusedElem,r=e.selectionRange;if(t!==n&&n&&n.ownerDocument&&kr(n.ownerDocument.documentElement,n)){if(r!==null&&jr(n)){if(t=r.start,e=r.end,e===void 0&&(e=t),`selectionStart`in n)n.selectionStart=t,n.selectionEnd=Math.min(e,n.value.length);else if(e=(t=n.ownerDocument||document)&&t.defaultView||window,e.getSelection){e=e.getSelection();var i=n.textContent.length,a=Math.min(r.start,i);r=r.end===void 0?a:Math.min(r.end,i),!e.extend&&a>r&&(i=r,r=a,a=i),i=Or(n,a);var o=Or(n,r);i&&o&&(e.rangeCount!==1||e.anchorNode!==i.node||e.anchorOffset!==i.offset||e.focusNode!==o.node||e.focusOffset!==o.offset)&&(t=t.createRange(),t.setStart(i.node,i.offset),e.removeAllRanges(),a>r?(e.addRange(t),e.extend(o.node,o.offset)):(t.setEnd(o.node,o.offset),e.addRange(t)))}}for(t=[],e=n;e=e.parentNode;)e.nodeType===1&&t.push({element:e,left:e.scrollLeft,top:e.scrollTop});for(typeof n.focus==`function`&&n.focus(),n=0;n<t.length;n++)e=t[n],e.element.scrollLeft=e.left,e.element.scrollTop=e.top}}var Nr=c&&`documentMode`in document&&11>=document.documentMode,Pr=null,Fr=null,Ir=null,Lr=!1;function Rr(e,t,n){var r=n.window===n?n.document:n.nodeType===9?n:n.ownerDocument;Lr||Pr==null||Pr!==me(r)||(r=Pr,`selectionStart`in r&&jr(r)?r={start:r.selectionStart,end:r.selectionEnd}:(r=(r.ownerDocument&&r.ownerDocument.defaultView||window).getSelection(),r={anchorNode:r.anchorNode,anchorOffset:r.anchorOffset,focusNode:r.focusNode,focusOffset:r.focusOffset}),Ir&&Er(Ir,r)||(Ir=r,r=ui(Fr,`onSelect`),0<r.length&&(t=new On(`onSelect`,`select`,null,t,n),e.push({event:t,listeners:r}),t.target=Pr)))}function zr(e,t){var n={};return n[e.toLowerCase()]=t.toLowerCase(),n[`Webkit`+e]=`webkit`+t,n[`Moz`+e]=`moz`+t,n}var Br={animationend:zr(`Animation`,`AnimationEnd`),animationiteration:zr(`Animation`,`AnimationIteration`),animationstart:zr(`Animation`,`AnimationStart`),transitionend:zr(`Transition`,`TransitionEnd`)},Vr={},Hr={};c&&(Hr=document.createElement(`div`).style,`AnimationEvent`in window||(delete Br.animationend.animation,delete Br.animationiteration.animation,delete Br.animationstart.animation),`TransitionEvent`in window||delete Br.transitionend.transition);function Ur(e){if(Vr[e])return Vr[e];if(!Br[e])return e;var t=Br[e],n;for(n in t)if(t.hasOwnProperty(n)&&n in Hr)return Vr[e]=t[n];return e}var Wr=Ur(`animationend`),Gr=Ur(`animationiteration`),Kr=Ur(`animationstart`),qr=Ur(`transitionend`),Jr=new Map,Yr=`abort auxClick cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel`.split(` `);function Xr(e,t){Jr.set(e,t),o(t,[e])}for(var Zr=0;Zr<Yr.length;Zr++){var Qr=Yr[Zr];Xr(Qr.toLowerCase(),`on`+(Qr[0].toUpperCase()+Qr.slice(1)))}Xr(Wr,`onAnimationEnd`),Xr(Gr,`onAnimationIteration`),Xr(Kr,`onAnimationStart`),Xr(`dblclick`,`onDoubleClick`),Xr(`focusin`,`onFocus`),Xr(`focusout`,`onBlur`),Xr(qr,`onTransitionEnd`),s(`onMouseEnter`,[`mouseout`,`mouseover`]),s(`onMouseLeave`,[`mouseout`,`mouseover`]),s(`onPointerEnter`,[`pointerout`,`pointerover`]),s(`onPointerLeave`,[`pointerout`,`pointerover`]),o(`onChange`,`change click focusin focusout input keydown keyup selectionchange`.split(` `)),o(`onSelect`,`focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange`.split(` `)),o(`onBeforeInput`,[`compositionend`,`keypress`,`textInput`,`paste`]),o(`onCompositionEnd`,`compositionend focusout keydown keypress keyup mousedown`.split(` `)),o(`onCompositionStart`,`compositionstart focusout keydown keypress keyup mousedown`.split(` `)),o(`onCompositionUpdate`,`compositionupdate focusout keydown keypress keyup mousedown`.split(` `));var $r=`abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting`.split(` `),ei=new Set(`cancel close invalid load scroll toggle`.split(` `).concat($r));function ti(e,t,n){var r=e.type||`unknown-event`;e.currentTarget=n,rt(r,t,void 0,e),e.currentTarget=null}function ni(e,t){t=!!(t&4);for(var n=0;n<e.length;n++){var r=e[n],i=r.event;r=r.listeners;a:{var a=void 0;if(t)for(var o=r.length-1;0<=o;o--){var s=r[o],c=s.instance,l=s.currentTarget;if(s=s.listener,c!==a&&i.isPropagationStopped())break a;ti(i,s,l),a=c}else for(o=0;o<r.length;o++){if(s=r[o],c=s.instance,l=s.currentTarget,s=s.listener,c!==a&&i.isPropagationStopped())break a;ti(i,s,l),a=c}}}if($e)throw e=et,$e=!1,et=null,e}function ri(e,t){var n=t[Ni];n===void 0&&(n=t[Ni]=new Set);var r=e+`__bubble`;n.has(r)||(si(t,e,2,!1),n.add(r))}function ii(e,t,n){var r=0;t&&(r|=4),si(n,e,r,t)}var ai=`_reactListening`+Math.random().toString(36).slice(2);function oi(e){if(!e[ai]){e[ai]=!0,i.forEach(function(t){t!==`selectionchange`&&(ei.has(t)||ii(t,!1,e),ii(t,!0,e))});var t=e.nodeType===9?e:e.ownerDocument;t===null||t[ai]||(t[ai]=!0,ii(`selectionchange`,!1,t))}}function si(e,t,n,r){switch(vn(t)){case 1:var i=pn;break;case 4:i=mn;break;default:i=hn}n=i.bind(null,t,n,e),i=void 0,!Je||t!==`touchstart`&&t!==`touchmove`&&t!==`wheel`||(i=!0),r?i===void 0?e.addEventListener(t,n,!0):e.addEventListener(t,n,{capture:!0,passive:i}):i===void 0?e.addEventListener(t,n,!1):e.addEventListener(t,n,{passive:i})}function ci(e,t,n,r,i){var a=r;if(!(t&1)&&!(t&2)&&r!==null)a:for(;;){if(r===null)return;var o=r.tag;if(o===3||o===4){var s=r.stateNode.containerInfo;if(s===i||s.nodeType===8&&s.parentNode===i)break;if(o===4)for(o=r.return;o!==null;){var c=o.tag;if((c===3||c===4)&&(c=o.stateNode.containerInfo,c===i||c.nodeType===8&&c.parentNode===i))return;o=o.return}for(;s!==null;){if(o=Ii(s),o===null)return;if(c=o.tag,c===5||c===6){r=a=o;continue a}s=s.parentNode}}r=r.return}Ke(function(){var r=a,i=Ie(n),o=[];a:{var s=Jr.get(e);if(s!==void 0){var c=On,l=e;switch(e){case`keypress`:if(Cn(n)===0)break a;case`keydown`:case`keyup`:c=Kn;break;case`focusin`:l=`focus`,c=Ln;break;case`focusout`:l=`blur`,c=Ln;break;case`beforeblur`:case`afterblur`:c=Ln;break;case`click`:if(n.button===2)break a;case`auxclick`:case`dblclick`:case`mousedown`:case`mousemove`:case`mouseup`:case`mouseout`:case`mouseover`:case`contextmenu`:c=Fn;break;case`drag`:case`dragend`:case`dragenter`:case`dragexit`:case`dragleave`:case`dragover`:case`dragstart`:case`drop`:c=In;break;case`touchcancel`:case`touchend`:case`touchmove`:case`touchstart`:c=qn;break;case Wr:case Gr:case Kr:c=Rn;break;case qr:c=Jn;break;case`scroll`:c=An;break;case`wheel`:c=Yn;break;case`copy`:case`cut`:case`paste`:c=zn;break;case`gotpointercapture`:case`lostpointercapture`:case`pointercancel`:case`pointerdown`:case`pointermove`:case`pointerout`:case`pointerover`:case`pointerup`:c=U}var u=!!(t&4),d=!u&&e===`scroll`,f=u?s===null?null:s+`Capture`:s;u=[];for(var p=r,m;p!==null;){m=p;var h=m.stateNode;if(m.tag===5&&h!==null&&(m=h,f!==null&&(h=qe(p,f),h!=null&&u.push(li(p,h,m)))),d)break;p=p.return}0<u.length&&(s=new c(s,l,null,n,i),o.push({event:s,listeners:u}))}}if(!(t&7)){a:{if(s=e===`mouseover`||e===`pointerover`,c=e===`mouseout`||e===`pointerout`,s&&n!==Fe&&(l=n.relatedTarget||n.fromElement)&&(Ii(l)||l[Mi]))break a;if((c||s)&&(s=i.window===i?i:(s=i.ownerDocument)?s.defaultView||s.parentWindow:window,c?(l=n.relatedTarget||n.toElement,c=r,l=l?Ii(l):null,l!==null&&(d=it(l),l!==d||l.tag!==5&&l.tag!==6)&&(l=null)):(c=null,l=r),c!==l)){if(u=Fn,h=`onMouseLeave`,f=`onMouseEnter`,p=`mouse`,(e===`pointerout`||e===`pointerover`)&&(u=U,h=`onPointerLeave`,f=`onPointerEnter`,p=`pointer`),d=c==null?s:Ri(c),m=l==null?s:Ri(l),s=new u(h,p+`leave`,c,n,i),s.target=d,s.relatedTarget=m,h=null,Ii(i)===r&&(u=new u(f,p+`enter`,l,n,i),u.target=m,u.relatedTarget=d,h=u),d=h,c&&l)b:{for(u=c,f=l,p=0,m=u;m;m=di(m))p++;for(m=0,h=f;h;h=di(h))m++;for(;0<p-m;)u=di(u),p--;for(;0<m-p;)f=di(f),m--;for(;p--;){if(u===f||f!==null&&u===f.alternate)break b;u=di(u),f=di(f)}u=null}else u=null;c!==null&&fi(o,s,c,u,!1),l!==null&&d!==null&&fi(o,d,l,u,!0)}}a:{if(s=r?Ri(r):window,c=s.nodeName&&s.nodeName.toLowerCase(),c===`select`||c===`input`&&s.type===`file`)var g=pr;else if(sr(s)){if(mr)g=Cr;else{g=xr;var _=br}}else(c=s.nodeName)&&c.toLowerCase()===`input`&&(s.type===`checkbox`||s.type===`radio`)&&(g=Sr);if(g&&=g(e,r)){cr(o,g,n,i);break a}_&&_(e,s,r),e===`focusout`&&(_=s._wrapperState)&&_.controlled&&s.type===`number`&&R(s,`number`,s.value)}switch(_=r?Ri(r):window,e){case`focusin`:(sr(_)||_.contentEditable===`true`)&&(Pr=_,Fr=r,Ir=null);break;case`focusout`:Ir=Fr=Pr=null;break;case`mousedown`:Lr=!0;break;case`contextmenu`:case`mouseup`:case`dragend`:Lr=!1,Rr(o,n,i);break;case`selectionchange`:if(Nr)break;case`keydown`:case`keyup`:Rr(o,n,i)}var v;if(Xn)b:{switch(e){case`compositionstart`:var y=`onCompositionStart`;break b;case`compositionend`:y=`onCompositionEnd`;break b;case`compositionupdate`:y=`onCompositionUpdate`;break b}y=void 0}else rr?tr(e,n)&&(y=`onCompositionEnd`):e===`keydown`&&n.keyCode===229&&(y=`onCompositionStart`);y&&($n&&n.locale!==`ko`&&(rr||y!==`onCompositionStart`?y===`onCompositionEnd`&&rr&&(v=Sn()):(yn=i,bn=`value`in yn?yn.value:yn.textContent,rr=!0)),_=ui(r,y),0<_.length&&(y=new Bn(y,e,null,n,i),o.push({event:y,listeners:_}),v?y.data=v:(v=nr(n),v!==null&&(y.data=v)))),(v=Qn?ir(e,n):ar(e,n))&&(r=ui(r,`onBeforeInput`),0<r.length&&(i=new Bn(`onBeforeInput`,`beforeinput`,null,n,i),o.push({event:i,listeners:r}),i.data=v))}ni(o,t)})}function li(e,t,n){return{instance:e,listener:t,currentTarget:n}}function ui(e,t){for(var n=t+`Capture`,r=[];e!==null;){var i=e,a=i.stateNode;i.tag===5&&a!==null&&(i=a,a=qe(e,n),a!=null&&r.unshift(li(e,a,i)),a=qe(e,t),a!=null&&r.push(li(e,a,i))),e=e.return}return r}function di(e){if(e===null)return null;do e=e.return;while(e&&e.tag!==5);return e||null}function fi(e,t,n,r,i){for(var a=t._reactName,o=[];n!==null&&n!==r;){var s=n,c=s.alternate,l=s.stateNode;if(c!==null&&c===r)break;s.tag===5&&l!==null&&(s=l,i?(c=qe(n,a),c!=null&&o.unshift(li(n,c,s))):i||(c=qe(n,a),c!=null&&o.push(li(n,c,s)))),n=n.return}o.length!==0&&e.push({event:t,listeners:o})}var pi=/\r\n?/g,mi=/\u0000|\uFFFD/g;function hi(e){return(typeof e==`string`?e:``+e).replace(pi,`
`).replace(mi,``)}function gi(e,t,n){if(t=hi(t),hi(e)!==t&&n)throw Error(r(425))}function _i(){}var vi=null,yi=null;function bi(e,t){return e===`textarea`||e===`noscript`||typeof t.children==`string`||typeof t.children==`number`||typeof t.dangerouslySetInnerHTML==`object`&&t.dangerouslySetInnerHTML!==null&&t.dangerouslySetInnerHTML.__html!=null}var xi=typeof setTimeout==`function`?setTimeout:void 0,Si=typeof clearTimeout==`function`?clearTimeout:void 0,Ci=typeof Promise==`function`?Promise:void 0,wi=typeof queueMicrotask==`function`?queueMicrotask:Ci===void 0?xi:function(e){return Ci.resolve(null).then(e).catch(Ti)};function Ti(e){setTimeout(function(){throw e})}function Ei(e,t){var n=t,r=0;do{var i=n.nextSibling;if(e.removeChild(n),i&&i.nodeType===8){if(n=i.data,n===`/$`){if(r===0){e.removeChild(i),un(t);return}r--}else n!==`$`&&n!==`$?`&&n!==`$!`||r++}n=i}while(n);un(t)}function Di(e){for(;e!=null;e=e.nextSibling){var t=e.nodeType;if(t===1||t===3)break;if(t===8){if(t=e.data,t===`$`||t===`$!`||t===`$?`)break;if(t===`/$`)return null}}return e}function Oi(e){e=e.previousSibling;for(var t=0;e;){if(e.nodeType===8){var n=e.data;if(n===`$`||n===`$!`||n===`$?`){if(t===0)return e;t--}else n===`/$`&&t++}e=e.previousSibling}return null}var ki=Math.random().toString(36).slice(2),Ai=`__reactFiber$`+ki,ji=`__reactProps$`+ki,Mi=`__reactContainer$`+ki,Ni=`__reactEvents$`+ki,Pi=`__reactListeners$`+ki,Fi=`__reactHandles$`+ki;function Ii(e){var t=e[Ai];if(t)return t;for(var n=e.parentNode;n;){if(t=n[Mi]||n[Ai]){if(n=t.alternate,t.child!==null||n!==null&&n.child!==null)for(e=Oi(e);e!==null;){if(n=e[Ai])return n;e=Oi(e)}return t}e=n,n=e.parentNode}return null}function Li(e){return e=e[Ai]||e[Mi],!e||e.tag!==5&&e.tag!==6&&e.tag!==13&&e.tag!==3?null:e}function Ri(e){if(e.tag===5||e.tag===6)return e.stateNode;throw Error(r(33))}function zi(e){return e[ji]||null}var Bi=[],Vi=-1;function Hi(e){return{current:e}}function Ui(e){0>Vi||(e.current=Bi[Vi],Bi[Vi]=null,Vi--)}function Wi(e,t){Vi++,Bi[Vi]=e.current,e.current=t}var Gi={},Ki=Hi(Gi),qi=Hi(!1),Ji=Gi;function Yi(e,t){var n=e.type.contextTypes;if(!n)return Gi;var r=e.stateNode;if(r&&r.__reactInternalMemoizedUnmaskedChildContext===t)return r.__reactInternalMemoizedMaskedChildContext;var i={},a;for(a in n)i[a]=t[a];return r&&(e=e.stateNode,e.__reactInternalMemoizedUnmaskedChildContext=t,e.__reactInternalMemoizedMaskedChildContext=i),i}function Xi(e){return e=e.childContextTypes,e!=null}function Zi(){Ui(qi),Ui(Ki)}function Qi(e,t,n){if(Ki.current!==Gi)throw Error(r(168));Wi(Ki,t),Wi(qi,n)}function $i(e,t,n){var i=e.stateNode;if(t=t.childContextTypes,typeof i.getChildContext!=`function`)return n;for(var a in i=i.getChildContext(),i)if(!(a in t))throw Error(r(108,ce(e)||`Unknown`,a));return L({},n,i)}function ea(e){return e=(e=e.stateNode)&&e.__reactInternalMemoizedMergedChildContext||Gi,Ji=Ki.current,Wi(Ki,e),Wi(qi,qi.current),!0}function ta(e,t,n){var i=e.stateNode;if(!i)throw Error(r(169));n?(e=$i(e,t,Ji),i.__reactInternalMemoizedMergedChildContext=e,Ui(qi),Ui(Ki),Wi(Ki,e)):Ui(qi),Wi(qi,n)}var na=null,ra=!1,ia=!1;function aa(e){na===null?na=[e]:na.push(e)}function oa(e){ra=!0,aa(e)}function sa(){if(!ia&&na!==null){ia=!0;var e=0,t=zt;try{var n=na;for(zt=1;e<n.length;e++){var r=n[e];do r=r(!0);while(r!==null)}na=null,ra=!1}catch(t){throw na!==null&&(na=na.slice(e+1)),ut(gt,sa),t}finally{zt=t,ia=!1}}return null}var ca=[],la=0,ua=null,da=0,fa=[],pa=0,ma=null,ha=1,ga=``;function _a(e,t){ca[la++]=da,ca[la++]=ua,ua=e,da=t}function va(e,t,n){fa[pa++]=ha,fa[pa++]=ga,fa[pa++]=ma,ma=e;var r=ha;e=ga;var i=32-wt(r)-1;r&=~(1<<i),n+=1;var a=32-wt(t)+i;if(30<a){var o=i-i%5;a=(r&(1<<o)-1).toString(32),r>>=o,i-=o,ha=1<<32-wt(t)+i|n<<i|r,ga=a+e}else ha=1<<a|n<<i|r,ga=e}function ya(e){e.return!==null&&(_a(e,1),va(e,1,0))}function ba(e){for(;e===ua;)ua=ca[--la],ca[la]=null,da=ca[--la],ca[la]=null;for(;e===ma;)ma=fa[--pa],fa[pa]=null,ga=fa[--pa],fa[pa]=null,ha=fa[--pa],fa[pa]=null}var xa=null,Sa=null,Ca=!1,wa=null;function Ta(e,t){var n=ql(5,null,null,0);n.elementType=`DELETED`,n.stateNode=t,n.return=e,t=e.deletions,t===null?(e.deletions=[n],e.flags|=16):t.push(n)}function Ea(e,t){switch(e.tag){case 5:var n=e.type;return t=t.nodeType!==1||n.toLowerCase()!==t.nodeName.toLowerCase()?null:t,t!==null&&(e.stateNode=t,xa=e,Sa=Di(t.firstChild),!0);case 6:return t=e.pendingProps===``||t.nodeType!==3?null:t,t!==null&&(e.stateNode=t,xa=e,Sa=null,!0);case 13:return t=t.nodeType===8?t:null,t!==null&&(n=ma===null?null:{id:ha,overflow:ga},e.memoizedState={dehydrated:t,treeContext:n,retryLane:1073741824},n=ql(18,null,null,0),n.stateNode=t,n.return=e,e.child=n,xa=e,Sa=null,!0);default:return!1}}function Da(e){return!!(e.mode&1)&&!(e.flags&128)}function Oa(e){if(Ca){var t=Sa;if(t){var n=t;if(!Ea(e,t)){if(Da(e))throw Error(r(418));t=Di(n.nextSibling);var i=xa;t&&Ea(e,t)?Ta(i,n):(e.flags=e.flags&-4097|2,Ca=!1,xa=e)}}else{if(Da(e))throw Error(r(418));e.flags=e.flags&-4097|2,Ca=!1,xa=e}}}function ka(e){for(e=e.return;e!==null&&e.tag!==5&&e.tag!==3&&e.tag!==13;)e=e.return;xa=e}function Aa(e){if(e!==xa)return!1;if(!Ca)return ka(e),Ca=!0,!1;var t;if((t=e.tag!==3)&&!(t=e.tag!==5)&&(t=e.type,t=t!==`head`&&t!==`body`&&!bi(e.type,e.memoizedProps)),t&&=Sa){if(Da(e))throw ja(),Error(r(418));for(;t;)Ta(e,t),t=Di(t.nextSibling)}if(ka(e),e.tag===13){if(e=e.memoizedState,e=e===null?null:e.dehydrated,!e)throw Error(r(317));a:{for(e=e.nextSibling,t=0;e;){if(e.nodeType===8){var n=e.data;if(n===`/$`){if(t===0){Sa=Di(e.nextSibling);break a}t--}else n!==`$`&&n!==`$!`&&n!==`$?`||t++}e=e.nextSibling}Sa=null}}else Sa=xa?Di(e.stateNode.nextSibling):null;return!0}function ja(){for(var e=Sa;e;)e=Di(e.nextSibling)}function Ma(){Sa=xa=null,Ca=!1}function Na(e){wa===null?wa=[e]:wa.push(e)}var Pa=C.ReactCurrentBatchConfig;function Fa(e,t,n){if(e=n.ref,e!==null&&typeof e!=`function`&&typeof e!=`object`){if(n._owner){if(n=n._owner,n){if(n.tag!==1)throw Error(r(309));var i=n.stateNode}if(!i)throw Error(r(147,e));var a=i,o=``+e;return t!==null&&t.ref!==null&&typeof t.ref==`function`&&t.ref._stringRef===o?t.ref:(t=function(e){var t=a.refs;e===null?delete t[o]:t[o]=e},t._stringRef=o,t)}if(typeof e!=`string`)throw Error(r(284));if(!n._owner)throw Error(r(290,e))}return e}function Ia(e,t){throw e=Object.prototype.toString.call(t),Error(r(31,e===`[object Object]`?`object with keys {`+Object.keys(t).join(`, `)+`}`:e))}function La(e){var t=e._init;return t(e._payload)}function Ra(e){function t(t,n){if(e){var r=t.deletions;r===null?(t.deletions=[n],t.flags|=16):r.push(n)}}function n(n,r){if(!e)return null;for(;r!==null;)t(n,r),r=r.sibling;return null}function i(e,t){for(e=new Map;t!==null;)t.key===null?e.set(t.index,t):e.set(t.key,t),t=t.sibling;return e}function a(e,t){return e=Xl(e,t),e.index=0,e.sibling=null,e}function o(t,n,r){return t.index=r,e?(r=t.alternate,r===null?(t.flags|=2,n):(r=r.index,r<n?(t.flags|=2,n):r)):(t.flags|=1048576,n)}function s(t){return e&&t.alternate===null&&(t.flags|=2),t}function c(e,t,n,r){return t===null||t.tag!==6?(t=eu(n,e.mode,r),t.return=e,t):(t=a(t,n),t.return=e,t)}function l(e,t,n,r){var i=n.type;return i===E?d(e,t,n.props.children,r,n.key):t!==null&&(t.elementType===i||typeof i==`object`&&i&&i.$$typeof===F&&La(i)===t.type)?(r=a(t,n.props),r.ref=Fa(e,t,n),r.return=e,r):(r=Zl(n.type,n.key,n.props,null,e.mode,r),r.ref=Fa(e,t,n),r.return=e,r)}function u(e,t,n,r){return t===null||t.tag!==4||t.stateNode.containerInfo!==n.containerInfo||t.stateNode.implementation!==n.implementation?(t=tu(n,e.mode,r),t.return=e,t):(t=a(t,n.children||[]),t.return=e,t)}function d(e,t,n,r,i){return t===null||t.tag!==7?(t=Ql(n,e.mode,r,i),t.return=e,t):(t=a(t,n),t.return=e,t)}function f(e,t,n){if(typeof t==`string`&&t!==``||typeof t==`number`)return t=eu(``+t,e.mode,n),t.return=e,t;if(typeof t==`object`&&t){switch(t.$$typeof){case w:return n=Zl(t.type,t.key,t.props,null,e.mode,n),n.ref=Fa(e,null,t),n.return=e,n;case T:return t=tu(t,e.mode,n),t.return=e,t;case F:var r=t._init;return f(e,r(t._payload),n)}if(be(t)||I(t))return t=Ql(t,e.mode,n,null),t.return=e,t;Ia(e,t)}return null}function p(e,t,n,r){var i=t===null?null:t.key;if(typeof n==`string`&&n!==``||typeof n==`number`)return i===null?c(e,t,``+n,r):null;if(typeof n==`object`&&n){switch(n.$$typeof){case w:return n.key===i?l(e,t,n,r):null;case T:return n.key===i?u(e,t,n,r):null;case F:return i=n._init,p(e,t,i(n._payload),r)}if(be(n)||I(n))return i===null?d(e,t,n,r,null):null;Ia(e,n)}return null}function m(e,t,n,r,i){if(typeof r==`string`&&r!==``||typeof r==`number`)return e=e.get(n)||null,c(t,e,``+r,i);if(typeof r==`object`&&r){switch(r.$$typeof){case w:return e=e.get(r.key===null?n:r.key)||null,l(t,e,r,i);case T:return e=e.get(r.key===null?n:r.key)||null,u(t,e,r,i);case F:var a=r._init;return m(e,t,n,a(r._payload),i)}if(be(r)||I(r))return e=e.get(n)||null,d(t,e,r,i,null);Ia(t,r)}return null}function h(r,a,s,c){for(var l=null,u=null,d=a,h=a=0,g=null;d!==null&&h<s.length;h++){d.index>h?(g=d,d=null):g=d.sibling;var _=p(r,d,s[h],c);if(_===null){d===null&&(d=g);break}e&&d&&_.alternate===null&&t(r,d),a=o(_,a,h),u===null?l=_:u.sibling=_,u=_,d=g}if(h===s.length)return n(r,d),Ca&&_a(r,h),l;if(d===null){for(;h<s.length;h++)d=f(r,s[h],c),d!==null&&(a=o(d,a,h),u===null?l=d:u.sibling=d,u=d);return Ca&&_a(r,h),l}for(d=i(r,d);h<s.length;h++)g=m(d,r,h,s[h],c),g!==null&&(e&&g.alternate!==null&&d.delete(g.key===null?h:g.key),a=o(g,a,h),u===null?l=g:u.sibling=g,u=g);return e&&d.forEach(function(e){return t(r,e)}),Ca&&_a(r,h),l}function g(a,s,c,l){var u=I(c);if(typeof u!=`function`)throw Error(r(150));if(c=u.call(c),c==null)throw Error(r(151));for(var d=u=null,h=s,g=s=0,_=null,v=c.next();h!==null&&!v.done;g++,v=c.next()){h.index>g?(_=h,h=null):_=h.sibling;var y=p(a,h,v.value,l);if(y===null){h===null&&(h=_);break}e&&h&&y.alternate===null&&t(a,h),s=o(y,s,g),d===null?u=y:d.sibling=y,d=y,h=_}if(v.done)return n(a,h),Ca&&_a(a,g),u;if(h===null){for(;!v.done;g++,v=c.next())v=f(a,v.value,l),v!==null&&(s=o(v,s,g),d===null?u=v:d.sibling=v,d=v);return Ca&&_a(a,g),u}for(h=i(a,h);!v.done;g++,v=c.next())v=m(h,a,g,v.value,l),v!==null&&(e&&v.alternate!==null&&h.delete(v.key===null?g:v.key),s=o(v,s,g),d===null?u=v:d.sibling=v,d=v);return e&&h.forEach(function(e){return t(a,e)}),Ca&&_a(a,g),u}function _(e,r,i,o){if(typeof i==`object`&&i&&i.type===E&&i.key===null&&(i=i.props.children),typeof i==`object`&&i){switch(i.$$typeof){case w:a:{for(var c=i.key,l=r;l!==null;){if(l.key===c){if(c=i.type,c===E){if(l.tag===7){n(e,l.sibling),r=a(l,i.props.children),r.return=e,e=r;break a}}else if(l.elementType===c||typeof c==`object`&&c&&c.$$typeof===F&&La(c)===l.type){n(e,l.sibling),r=a(l,i.props),r.ref=Fa(e,l,i),r.return=e,e=r;break a}n(e,l);break}t(e,l),l=l.sibling}i.type===E?(r=Ql(i.props.children,e.mode,o,i.key),r.return=e,e=r):(o=Zl(i.type,i.key,i.props,null,e.mode,o),o.ref=Fa(e,r,i),o.return=e,e=o)}return s(e);case T:a:{for(l=i.key;r!==null;){if(r.key===l){if(r.tag===4&&r.stateNode.containerInfo===i.containerInfo&&r.stateNode.implementation===i.implementation){n(e,r.sibling),r=a(r,i.children||[]),r.return=e,e=r;break a}n(e,r);break}t(e,r),r=r.sibling}r=tu(i,e.mode,o),r.return=e,e=r}return s(e);case F:return l=i._init,_(e,r,l(i._payload),o)}if(be(i))return h(e,r,i,o);if(I(i))return g(e,r,i,o);Ia(e,i)}return typeof i==`string`&&i!==``||typeof i==`number`?(i=``+i,r!==null&&r.tag===6?(n(e,r.sibling),r=a(r,i),r.return=e,e=r):(n(e,r),r=eu(i,e.mode,o),r.return=e,e=r),s(e)):n(e,r)}return _}var za=Ra(!0),Ba=Ra(!1),Va=Hi(null),Ha=null,Ua=null,Wa=null;function Ga(){Wa=Ua=Ha=null}function Ka(e){var t=Va.current;Ui(Va),e._currentValue=t}function qa(e,t,n){for(;e!==null;){var r=e.alternate;if((e.childLanes&t)===t?r!==null&&(r.childLanes&t)!==t&&(r.childLanes|=t):(e.childLanes|=t,r!==null&&(r.childLanes|=t)),e===n)break;e=e.return}}function Ja(e,t){Ha=e,Wa=Ua=null,e=e.dependencies,e!==null&&e.firstContext!==null&&((e.lanes&t)!==0&&(Ms=!0),e.firstContext=null)}function Ya(e){var t=e._currentValue;if(Wa!==e){if(e={context:e,memoizedValue:t,next:null},Ua===null){if(Ha===null)throw Error(r(308));Ua=e,Ha.dependencies={lanes:0,firstContext:e}}else Ua=Ua.next=e}return t}var Xa=null;function Za(e){Xa===null?Xa=[e]:Xa.push(e)}function Qa(e,t,n,r){var i=t.interleaved;return i===null?(n.next=n,Za(t)):(n.next=i.next,i.next=n),t.interleaved=n,$a(e,r)}function $a(e,t){e.lanes|=t;var n=e.alternate;for(n!==null&&(n.lanes|=t),n=e,e=e.return;e!==null;)e.childLanes|=t,n=e.alternate,n!==null&&(n.childLanes|=t),n=e,e=e.return;return n.tag===3?n.stateNode:null}var eo=!1;function to(e){e.updateQueue={baseState:e.memoizedState,firstBaseUpdate:null,lastBaseUpdate:null,shared:{pending:null,interleaved:null,lanes:0},effects:null}}function no(e,t){e=e.updateQueue,t.updateQueue===e&&(t.updateQueue={baseState:e.baseState,firstBaseUpdate:e.firstBaseUpdate,lastBaseUpdate:e.lastBaseUpdate,shared:e.shared,effects:e.effects})}function ro(e,t){return{eventTime:e,lane:t,tag:0,payload:null,callback:null,next:null}}function io(e,t,n){var r=e.updateQueue;if(r===null)return null;if(r=r.shared,Vc&2){var i=r.pending;return i===null?t.next=t:(t.next=i.next,i.next=t),r.pending=t,$a(e,n)}return i=r.interleaved,i===null?(t.next=t,Za(r)):(t.next=i.next,i.next=t),r.interleaved=t,$a(e,n)}function ao(e,t,n){if(t=t.updateQueue,t!==null&&(t=t.shared,n&4194240)){var r=t.lanes;r&=e.pendingLanes,n|=r,t.lanes=n,Rt(e,n)}}function oo(e,t){var n=e.updateQueue,r=e.alternate;if(r!==null&&(r=r.updateQueue,n===r)){var i=null,a=null;if(n=n.firstBaseUpdate,n!==null){do{var o={eventTime:n.eventTime,lane:n.lane,tag:n.tag,payload:n.payload,callback:n.callback,next:null};a===null?i=a=o:a=a.next=o,n=n.next}while(n!==null);a===null?i=a=t:a=a.next=t}else i=a=t;n={baseState:r.baseState,firstBaseUpdate:i,lastBaseUpdate:a,shared:r.shared,effects:r.effects},e.updateQueue=n;return}e=n.lastBaseUpdate,e===null?n.firstBaseUpdate=t:e.next=t,n.lastBaseUpdate=t}function so(e,t,n,r){var i=e.updateQueue;eo=!1;var a=i.firstBaseUpdate,o=i.lastBaseUpdate,s=i.shared.pending;if(s!==null){i.shared.pending=null;var c=s,l=c.next;c.next=null,o===null?a=l:o.next=l,o=c;var u=e.alternate;u!==null&&(u=u.updateQueue,s=u.lastBaseUpdate,s!==o&&(s===null?u.firstBaseUpdate=l:s.next=l,u.lastBaseUpdate=c))}if(a!==null){var d=i.baseState;o=0,u=l=c=null,s=a;do{var f=s.lane,p=s.eventTime;if((r&f)===f){u!==null&&(u=u.next={eventTime:p,lane:0,tag:s.tag,payload:s.payload,callback:s.callback,next:null});a:{var m=e,h=s;switch(f=t,p=n,h.tag){case 1:if(m=h.payload,typeof m==`function`){d=m.call(p,d,f);break a}d=m;break a;case 3:m.flags=m.flags&-65537|128;case 0:if(m=h.payload,f=typeof m==`function`?m.call(p,d,f):m,f==null)break a;d=L({},d,f);break a;case 2:eo=!0}}s.callback!==null&&s.lane!==0&&(e.flags|=64,f=i.effects,f===null?i.effects=[s]:f.push(s))}else p={eventTime:p,lane:f,tag:s.tag,payload:s.payload,callback:s.callback,next:null},u===null?(l=u=p,c=d):u=u.next=p,o|=f;if(s=s.next,s===null){if(s=i.shared.pending,s===null)break;f=s,s=f.next,f.next=null,i.lastBaseUpdate=f,i.shared.pending=null}}while(1);if(u===null&&(c=d),i.baseState=c,i.firstBaseUpdate=l,i.lastBaseUpdate=u,t=i.shared.interleaved,t!==null){i=t;do o|=i.lane,i=i.next;while(i!==t)}else a===null&&(i.shared.lanes=0);Yc|=o,e.lanes=o,e.memoizedState=d}}function co(e,t,n){if(e=t.effects,t.effects=null,e!==null)for(t=0;t<e.length;t++){var i=e[t],a=i.callback;if(a!==null){if(i.callback=null,i=n,typeof a!=`function`)throw Error(r(191,a));a.call(i)}}}var lo={},uo=Hi(lo),fo=Hi(lo),po=Hi(lo);function mo(e){if(e===lo)throw Error(r(174));return e}function ho(e,t){switch(Wi(po,t),Wi(fo,e),Wi(uo,lo),e=t.nodeType,e){case 9:case 11:t=(t=t.documentElement)?t.namespaceURI:we(null,``);break;default:e=e===8?t.parentNode:t,t=e.namespaceURI||null,e=e.tagName,t=we(t,e)}Ui(uo),Wi(uo,t)}function go(){Ui(uo),Ui(fo),Ui(po)}function _o(e){mo(po.current);var t=mo(uo.current),n=we(t,e.type);t!==n&&(Wi(fo,e),Wi(uo,n))}function vo(e){fo.current===e&&(Ui(uo),Ui(fo))}var yo=Hi(0);function bo(e){for(var t=e;t!==null;){if(t.tag===13){var n=t.memoizedState;if(n!==null&&(n=n.dehydrated,n===null||n.data===`$?`||n.data===`$!`))return t}else if(t.tag===19&&t.memoizedProps.revealOrder!==void 0){if(t.flags&128)return t}else if(t.child!==null){t.child.return=t,t=t.child;continue}if(t===e)break;for(;t.sibling===null;){if(t.return===null||t.return===e)return null;t=t.return}t.sibling.return=t.return,t=t.sibling}return null}var xo=[];function So(){for(var e=0;e<xo.length;e++)xo[e]._workInProgressVersionPrimary=null;xo.length=0}var Co=C.ReactCurrentDispatcher,wo=C.ReactCurrentBatchConfig,To=0,Eo=null,Do=null,Oo=null,ko=!1,Ao=!1,jo=0,Mo=0;function No(){throw Error(r(321))}function Po(e,t){if(t===null)return!1;for(var n=0;n<t.length&&n<e.length;n++)if(!Tr(e[n],t[n]))return!1;return!0}function K(e,t,n,i,a,o){if(To=o,Eo=t,t.memoizedState=null,t.updateQueue=null,t.lanes=0,Co.current=e===null||e.memoizedState===null?ps:Z,e=n(i,a),Ao){o=0;do{if(Ao=!1,jo=0,25<=o)throw Error(r(301));o+=1,Oo=Do=null,t.updateQueue=null,Co.current=ms,e=n(i,a)}while(Ao)}if(Co.current=fs,t=Do!==null&&Do.next!==null,To=0,Oo=Do=Eo=null,ko=!1,t)throw Error(r(300));return e}function q(){var e=jo!==0;return jo=0,e}function Fo(){var e={memoizedState:null,baseState:null,baseQueue:null,queue:null,next:null};return Oo===null?Eo.memoizedState=Oo=e:Oo=Oo.next=e,Oo}function Io(){if(Do===null){var e=Eo.alternate;e=e===null?null:e.memoizedState}else e=Do.next;var t=Oo===null?Eo.memoizedState:Oo.next;if(t!==null)Oo=t,Do=e;else{if(e===null)throw Error(r(310));Do=e,e={memoizedState:Do.memoizedState,baseState:Do.baseState,baseQueue:Do.baseQueue,queue:Do.queue,next:null},Oo===null?Eo.memoizedState=Oo=e:Oo=Oo.next=e}return Oo}function Lo(e,t){return typeof t==`function`?t(e):t}function Ro(e){var t=Io(),n=t.queue;if(n===null)throw Error(r(311));n.lastRenderedReducer=e;var i=Do,a=i.baseQueue,o=n.pending;if(o!==null){if(a!==null){var s=a.next;a.next=o.next,o.next=s}i.baseQueue=a=o,n.pending=null}if(a!==null){o=a.next,i=i.baseState;var c=s=null,l=null,u=o;do{var d=u.lane;if((To&d)===d)l!==null&&(l=l.next={lane:0,action:u.action,hasEagerState:u.hasEagerState,eagerState:u.eagerState,next:null}),i=u.hasEagerState?u.eagerState:e(i,u.action);else{var f={lane:d,action:u.action,hasEagerState:u.hasEagerState,eagerState:u.eagerState,next:null};l===null?(c=l=f,s=i):l=l.next=f,Eo.lanes|=d,Yc|=d}u=u.next}while(u!==null&&u!==o);l===null?s=i:l.next=c,Tr(i,t.memoizedState)||(Ms=!0),t.memoizedState=i,t.baseState=s,t.baseQueue=l,n.lastRenderedState=i}if(e=n.interleaved,e!==null){a=e;do o=a.lane,Eo.lanes|=o,Yc|=o,a=a.next;while(a!==e)}else a===null&&(n.lanes=0);return[t.memoizedState,n.dispatch]}function zo(e){var t=Io(),n=t.queue;if(n===null)throw Error(r(311));n.lastRenderedReducer=e;var i=n.dispatch,a=n.pending,o=t.memoizedState;if(a!==null){n.pending=null;var s=a=a.next;do o=e(o,s.action),s=s.next;while(s!==a);Tr(o,t.memoizedState)||(Ms=!0),t.memoizedState=o,t.baseQueue===null&&(t.baseState=o),n.lastRenderedState=o}return[o,i]}function Bo(){}function Vo(e,t){var n=Eo,i=Io(),a=t(),o=!Tr(i.memoizedState,a);if(o&&(i.memoizedState=a,Ms=!0),i=i.queue,Qo(J.bind(null,n,i,e),[e]),i.getSnapshot!==t||o||Oo!==null&&Oo.memoizedState.tag&1){if(n.flags|=2048,qo(9,Uo.bind(null,n,i,a,t),void 0,null),Hc===null)throw Error(r(349));To&30||Ho(n,t,a)}return a}function Ho(e,t,n){e.flags|=16384,e={getSnapshot:t,value:n},t=Eo.updateQueue,t===null?(t={lastEffect:null,stores:null},Eo.updateQueue=t,t.stores=[e]):(n=t.stores,n===null?t.stores=[e]:n.push(e))}function Uo(e,t,n,r){t.value=n,t.getSnapshot=r,Wo(t)&&Go(e)}function J(e,t,n){return n(function(){Wo(t)&&Go(e)})}function Wo(e){var t=e.getSnapshot;e=e.value;try{var n=t();return!Tr(e,n)}catch{return!0}}function Go(e){var t=$a(e,1);t!==null&&hl(t,e,1,-1)}function Ko(e){var t=Fo();return typeof e==`function`&&(e=e()),t.memoizedState=t.baseState=e,e={pending:null,interleaved:null,lanes:0,dispatch:null,lastRenderedReducer:Lo,lastRenderedState:e},t.queue=e,e=e.dispatch=us.bind(null,Eo,e),[t.memoizedState,e]}function qo(e,t,n,r){return e={tag:e,create:t,destroy:n,deps:r,next:null},t=Eo.updateQueue,t===null?(t={lastEffect:null,stores:null},Eo.updateQueue=t,t.lastEffect=e.next=e):(n=t.lastEffect,n===null?t.lastEffect=e.next=e:(r=n.next,n.next=e,e.next=r,t.lastEffect=e)),e}function Jo(){return Io().memoizedState}function Yo(e,t,n,r){var i=Fo();Eo.flags|=e,i.memoizedState=qo(1|t,n,void 0,r===void 0?null:r)}function Xo(e,t,n,r){var i=Io();r=r===void 0?null:r;var a=void 0;if(Do!==null){var o=Do.memoizedState;if(a=o.destroy,r!==null&&Po(r,o.deps)){i.memoizedState=qo(t,n,a,r);return}}Eo.flags|=e,i.memoizedState=qo(1|t,n,a,r)}function Zo(e,t){return Yo(8390656,8,e,t)}function Qo(e,t){return Xo(2048,8,e,t)}function $o(e,t){return Xo(4,2,e,t)}function es(e,t){return Xo(4,4,e,t)}function ts(e,t){if(typeof t==`function`)return e=e(),t(e),function(){t(null)};if(t!=null)return e=e(),t.current=e,function(){t.current=null}}function ns(e,t,n){return n=n==null?null:n.concat([e]),Xo(4,4,ts.bind(null,t,e),n)}function rs(){}function is(e,t){var n=Io();t=t===void 0?null:t;var r=n.memoizedState;return r!==null&&t!==null&&Po(t,r[1])?r[0]:(n.memoizedState=[e,t],e)}function as(e,t){var n=Io();t=t===void 0?null:t;var r=n.memoizedState;return r!==null&&t!==null&&Po(t,r[1])?r[0]:(e=e(),n.memoizedState=[e,t],e)}function os(e,t,n){return To&21?(Tr(n,t)||(n=Pt(),Eo.lanes|=n,Yc|=n,e.baseState=!0),t):(e.baseState&&(e.baseState=!1,Ms=!0),e.memoizedState=n)}function ss(e,t){var n=zt;zt=n!==0&&4>n?n:4,e(!0);var r=wo.transition;wo.transition={};try{e(!1),t()}finally{zt=n,wo.transition=r}}function cs(){return Io().memoizedState}function ls(e,t,n){var r=ml(e);if(n={lane:r,action:n,hasEagerState:!1,eagerState:null,next:null},Y(e))ds(t,n);else if(n=Qa(e,t,n,r),n!==null){var i=pl();hl(n,e,r,i),X(n,t,r)}}function us(e,t,n){var r=ml(e),i={lane:r,action:n,hasEagerState:!1,eagerState:null,next:null};if(Y(e))ds(t,i);else{var a=e.alternate;if(e.lanes===0&&(a===null||a.lanes===0)&&(a=t.lastRenderedReducer,a!==null))try{var o=t.lastRenderedState,s=a(o,n);if(i.hasEagerState=!0,i.eagerState=s,Tr(s,o)){var c=t.interleaved;c===null?(i.next=i,Za(t)):(i.next=c.next,c.next=i),t.interleaved=i;return}}catch{}n=Qa(e,t,i,r),n!==null&&(i=pl(),hl(n,e,r,i),X(n,t,r))}}function Y(e){var t=e.alternate;return e===Eo||t!==null&&t===Eo}function ds(e,t){Ao=ko=!0;var n=e.pending;n===null?t.next=t:(t.next=n.next,n.next=t),e.pending=t}function X(e,t,n){if(n&4194240){var r=t.lanes;r&=e.pendingLanes,n|=r,t.lanes=n,Rt(e,n)}}var fs={readContext:Ya,useCallback:No,useContext:No,useEffect:No,useImperativeHandle:No,useInsertionEffect:No,useLayoutEffect:No,useMemo:No,useReducer:No,useRef:No,useState:No,useDebugValue:No,useDeferredValue:No,useTransition:No,useMutableSource:No,useSyncExternalStore:No,useId:No,unstable_isNewReconciler:!1},ps={readContext:Ya,useCallback:function(e,t){return Fo().memoizedState=[e,t===void 0?null:t],e},useContext:Ya,useEffect:Zo,useImperativeHandle:function(e,t,n){return n=n==null?null:n.concat([e]),Yo(4194308,4,ts.bind(null,t,e),n)},useLayoutEffect:function(e,t){return Yo(4194308,4,e,t)},useInsertionEffect:function(e,t){return Yo(4,2,e,t)},useMemo:function(e,t){var n=Fo();return t=t===void 0?null:t,e=e(),n.memoizedState=[e,t],e},useReducer:function(e,t,n){var r=Fo();return t=n===void 0?t:n(t),r.memoizedState=r.baseState=t,e={pending:null,interleaved:null,lanes:0,dispatch:null,lastRenderedReducer:e,lastRenderedState:t},r.queue=e,e=e.dispatch=ls.bind(null,Eo,e),[r.memoizedState,e]},useRef:function(e){var t=Fo();return e={current:e},t.memoizedState=e},useState:Ko,useDebugValue:rs,useDeferredValue:function(e){return Fo().memoizedState=e},useTransition:function(){var e=Ko(!1),t=e[0];return e=ss.bind(null,e[1]),Fo().memoizedState=e,[t,e]},useMutableSource:function(){},useSyncExternalStore:function(e,t,n){var i=Eo,a=Fo();if(Ca){if(n===void 0)throw Error(r(407));n=n()}else{if(n=t(),Hc===null)throw Error(r(349));To&30||Ho(i,t,n)}a.memoizedState=n;var o={value:n,getSnapshot:t};return a.queue=o,Zo(J.bind(null,i,o,e),[e]),i.flags|=2048,qo(9,Uo.bind(null,i,o,n,t),void 0,null),n},useId:function(){var e=Fo(),t=Hc.identifierPrefix;if(Ca){var n=ga,r=ha;n=(r&~(1<<32-wt(r)-1)).toString(32)+n,t=`:`+t+`R`+n,n=jo++,0<n&&(t+=`H`+n.toString(32)),t+=`:`}else n=Mo++,t=`:`+t+`r`+n.toString(32)+`:`;return e.memoizedState=t},unstable_isNewReconciler:!1},Z={readContext:Ya,useCallback:is,useContext:Ya,useEffect:Qo,useImperativeHandle:ns,useInsertionEffect:$o,useLayoutEffect:es,useMemo:as,useReducer:Ro,useRef:Jo,useState:function(){return Ro(Lo)},useDebugValue:rs,useDeferredValue:function(e){return os(Io(),Do.memoizedState,e)},useTransition:function(){return[Ro(Lo)[0],Io().memoizedState]},useMutableSource:Bo,useSyncExternalStore:Vo,useId:cs,unstable_isNewReconciler:!1},ms={readContext:Ya,useCallback:is,useContext:Ya,useEffect:Qo,useImperativeHandle:ns,useInsertionEffect:$o,useLayoutEffect:es,useMemo:as,useReducer:zo,useRef:Jo,useState:function(){return zo(Lo)},useDebugValue:rs,useDeferredValue:function(e){var t=Io();return Do===null?t.memoizedState=e:os(t,Do.memoizedState,e)},useTransition:function(){return[zo(Lo)[0],Io().memoizedState]},useMutableSource:Bo,useSyncExternalStore:Vo,useId:cs,unstable_isNewReconciler:!1};function hs(e,t){if(e&&e.defaultProps){for(var n in t=L({},t),e=e.defaultProps,e)t[n]===void 0&&(t[n]=e[n]);return t}return t}function gs(e,t,n,r){t=e.memoizedState,n=n(r,t),n=n==null?t:L({},t,n),e.memoizedState=n,e.lanes===0&&(e.updateQueue.baseState=n)}var _s={isMounted:function(e){return(e=e._reactInternals)?it(e)===e:!1},enqueueSetState:function(e,t,n){e=e._reactInternals;var r=pl(),i=ml(e),a=ro(r,i);a.payload=t,n!=null&&(a.callback=n),t=io(e,a,i),t!==null&&(hl(t,e,i,r),ao(t,e,i))},enqueueReplaceState:function(e,t,n){e=e._reactInternals;var r=pl(),i=ml(e),a=ro(r,i);a.tag=1,a.payload=t,n!=null&&(a.callback=n),t=io(e,a,i),t!==null&&(hl(t,e,i,r),ao(t,e,i))},enqueueForceUpdate:function(e,t){e=e._reactInternals;var n=pl(),r=ml(e),i=ro(n,r);i.tag=2,t!=null&&(i.callback=t),t=io(e,i,r),t!==null&&(hl(t,e,r,n),ao(t,e,r))}};function vs(e,t,n,r,i,a,o){return e=e.stateNode,typeof e.shouldComponentUpdate==`function`?e.shouldComponentUpdate(r,a,o):t.prototype&&t.prototype.isPureReactComponent?!Er(n,r)||!Er(i,a):!0}function ys(e,t,n){var r=!1,i=Gi,a=t.contextType;return typeof a==`object`&&a?a=Ya(a):(i=Xi(t)?Ji:Ki.current,r=t.contextTypes,a=(r=r!=null)?Yi(e,i):Gi),t=new t(n,a),e.memoizedState=t.state!==null&&t.state!==void 0?t.state:null,t.updater=_s,e.stateNode=t,t._reactInternals=e,r&&(e=e.stateNode,e.__reactInternalMemoizedUnmaskedChildContext=i,e.__reactInternalMemoizedMaskedChildContext=a),t}function bs(e,t,n,r){e=t.state,typeof t.componentWillReceiveProps==`function`&&t.componentWillReceiveProps(n,r),typeof t.UNSAFE_componentWillReceiveProps==`function`&&t.UNSAFE_componentWillReceiveProps(n,r),t.state!==e&&_s.enqueueReplaceState(t,t.state,null)}function xs(e,t,n,r){var i=e.stateNode;i.props=n,i.state=e.memoizedState,i.refs={},to(e);var a=t.contextType;typeof a==`object`&&a?i.context=Ya(a):(a=Xi(t)?Ji:Ki.current,i.context=Yi(e,a)),i.state=e.memoizedState,a=t.getDerivedStateFromProps,typeof a==`function`&&(gs(e,t,a,n),i.state=e.memoizedState),typeof t.getDerivedStateFromProps==`function`||typeof i.getSnapshotBeforeUpdate==`function`||typeof i.UNSAFE_componentWillMount!=`function`&&typeof i.componentWillMount!=`function`||(t=i.state,typeof i.componentWillMount==`function`&&i.componentWillMount(),typeof i.UNSAFE_componentWillMount==`function`&&i.UNSAFE_componentWillMount(),t!==i.state&&_s.enqueueReplaceState(i,i.state,null),so(e,n,i,r),i.state=e.memoizedState),typeof i.componentDidMount==`function`&&(e.flags|=4194308)}function Ss(e,t){try{var n=``,r=t;do n+=oe(r),r=r.return;while(r);var i=n}catch(e){i=`
Error generating stack: `+e.message+`
`+e.stack}return{value:e,source:t,stack:i,digest:null}}function Cs(e,t,n){return{value:e,source:null,stack:n??null,digest:t??null}}function ws(e,t){try{console.error(t.value)}catch(e){setTimeout(function(){throw e})}}var Ts=typeof WeakMap==`function`?WeakMap:Map;function Es(e,t,n){n=ro(-1,n),n.tag=3,n.payload={element:null};var r=t.value;return n.callback=function(){rl||(rl=!0,il=r),ws(e,t)},n}function Ds(e,t,n){n=ro(-1,n),n.tag=3;var r=e.type.getDerivedStateFromError;if(typeof r==`function`){var i=t.value;n.payload=function(){return r(i)},n.callback=function(){ws(e,t)}}var a=e.stateNode;return a!==null&&typeof a.componentDidCatch==`function`&&(n.callback=function(){ws(e,t),typeof r!=`function`&&(al===null?al=new Set([this]):al.add(this));var n=t.stack;this.componentDidCatch(t.value,{componentStack:n===null?``:n})}),n}function Os(e,t,n){var r=e.pingCache;if(r===null){r=e.pingCache=new Ts;var i=new Set;r.set(t,i)}else i=r.get(t),i===void 0&&(i=new Set,r.set(t,i));i.has(n)||(i.add(n),e=Bl.bind(null,e,t,n),t.then(e,e))}function ks(e){do{var t;if((t=e.tag===13)&&(t=e.memoizedState,t=t===null||t.dehydrated!==null),t)return e;e=e.return}while(e!==null);return null}function As(e,t,n,r,i){return e.mode&1?(e.flags|=65536,e.lanes=i,e):(e===t?e.flags|=65536:(e.flags|=128,n.flags|=131072,n.flags&=-52805,n.tag===1&&(n.alternate===null?n.tag=17:(t=ro(-1,1),t.tag=2,io(n,t,1))),n.lanes|=1),e)}var js=C.ReactCurrentOwner,Ms=!1;function Ns(e,t,n,r){t.child=e===null?Ba(t,null,n,r):za(t,e.child,n,r)}function Ps(e,t,n,r,i){n=n.render;var a=t.ref;return Ja(t,i),r=K(e,t,n,r,a,i),n=q(),e!==null&&!Ms?(t.updateQueue=e.updateQueue,t.flags&=-2053,e.lanes&=~i,ec(e,t,i)):(Ca&&n&&ya(t),t.flags|=1,Ns(e,t,r,i),t.child)}function Fs(e,t,n,r,i){if(e===null){var a=n.type;return typeof a==`function`&&!Jl(a)&&a.defaultProps===void 0&&n.compare===null&&n.defaultProps===void 0?(t.tag=15,t.type=a,Is(e,t,a,r,i)):(e=Zl(n.type,null,r,t,t.mode,i),e.ref=t.ref,e.return=t,t.child=e)}if(a=e.child,(e.lanes&i)===0){var o=a.memoizedProps;if(n=n.compare,n=n===null?Er:n,n(o,r)&&e.ref===t.ref)return ec(e,t,i)}return t.flags|=1,e=Xl(a,r),e.ref=t.ref,e.return=t,t.child=e}function Is(e,t,n,r,i){if(e!==null){var a=e.memoizedProps;if(Er(a,r)&&e.ref===t.ref){if(Ms=!1,t.pendingProps=r=a,(e.lanes&i)!==0)e.flags&131072&&(Ms=!0);else return t.lanes=e.lanes,ec(e,t,i)}}return zs(e,t,n,r,i)}function Ls(e,t,n){var r=t.pendingProps,i=r.children,a=e===null?null:e.memoizedState;if(r.mode===`hidden`){if(!(t.mode&1))t.memoizedState={baseLanes:0,cachePool:null,transitions:null},Wi(Kc,Gc),Gc|=n;else{if(!(n&1073741824))return e=a===null?n:a.baseLanes|n,t.lanes=t.childLanes=1073741824,t.memoizedState={baseLanes:e,cachePool:null,transitions:null},t.updateQueue=null,Wi(Kc,Gc),Gc|=e,null;t.memoizedState={baseLanes:0,cachePool:null,transitions:null},r=a===null?n:a.baseLanes,Wi(Kc,Gc),Gc|=r}}else a===null?r=n:(r=a.baseLanes|n,t.memoizedState=null),Wi(Kc,Gc),Gc|=r;return Ns(e,t,i,n),t.child}function Rs(e,t){var n=t.ref;(e===null&&n!==null||e!==null&&e.ref!==n)&&(t.flags|=512,t.flags|=2097152)}function zs(e,t,n,r,i){var a=Xi(n)?Ji:Ki.current;return a=Yi(t,a),Ja(t,i),n=K(e,t,n,r,a,i),r=q(),e!==null&&!Ms?(t.updateQueue=e.updateQueue,t.flags&=-2053,e.lanes&=~i,ec(e,t,i)):(Ca&&r&&ya(t),t.flags|=1,Ns(e,t,n,i),t.child)}function Bs(e,t,n,r,i){if(Xi(n)){var a=!0;ea(t)}else a=!1;if(Ja(t,i),t.stateNode===null)$s(e,t),ys(t,n,r),xs(t,n,r,i),r=!0;else if(e===null){var o=t.stateNode,s=t.memoizedProps;o.props=s;var c=o.context,l=n.contextType;typeof l==`object`&&l?l=Ya(l):(l=Xi(n)?Ji:Ki.current,l=Yi(t,l));var u=n.getDerivedStateFromProps,d=typeof u==`function`||typeof o.getSnapshotBeforeUpdate==`function`;d||typeof o.UNSAFE_componentWillReceiveProps!=`function`&&typeof o.componentWillReceiveProps!=`function`||(s!==r||c!==l)&&bs(t,o,r,l),eo=!1;var f=t.memoizedState;o.state=f,so(t,r,o,i),c=t.memoizedState,s!==r||f!==c||qi.current||eo?(typeof u==`function`&&(gs(t,n,u,r),c=t.memoizedState),(s=eo||vs(t,n,s,r,f,c,l))?(d||typeof o.UNSAFE_componentWillMount!=`function`&&typeof o.componentWillMount!=`function`||(typeof o.componentWillMount==`function`&&o.componentWillMount(),typeof o.UNSAFE_componentWillMount==`function`&&o.UNSAFE_componentWillMount()),typeof o.componentDidMount==`function`&&(t.flags|=4194308)):(typeof o.componentDidMount==`function`&&(t.flags|=4194308),t.memoizedProps=r,t.memoizedState=c),o.props=r,o.state=c,o.context=l,r=s):(typeof o.componentDidMount==`function`&&(t.flags|=4194308),r=!1)}else{o=t.stateNode,no(e,t),s=t.memoizedProps,l=t.type===t.elementType?s:hs(t.type,s),o.props=l,d=t.pendingProps,f=o.context,c=n.contextType,typeof c==`object`&&c?c=Ya(c):(c=Xi(n)?Ji:Ki.current,c=Yi(t,c));var p=n.getDerivedStateFromProps;(u=typeof p==`function`||typeof o.getSnapshotBeforeUpdate==`function`)||typeof o.UNSAFE_componentWillReceiveProps!=`function`&&typeof o.componentWillReceiveProps!=`function`||(s!==d||f!==c)&&bs(t,o,r,c),eo=!1,f=t.memoizedState,o.state=f,so(t,r,o,i);var m=t.memoizedState;s!==d||f!==m||qi.current||eo?(typeof p==`function`&&(gs(t,n,p,r),m=t.memoizedState),(l=eo||vs(t,n,l,r,f,m,c)||!1)?(u||typeof o.UNSAFE_componentWillUpdate!=`function`&&typeof o.componentWillUpdate!=`function`||(typeof o.componentWillUpdate==`function`&&o.componentWillUpdate(r,m,c),typeof o.UNSAFE_componentWillUpdate==`function`&&o.UNSAFE_componentWillUpdate(r,m,c)),typeof o.componentDidUpdate==`function`&&(t.flags|=4),typeof o.getSnapshotBeforeUpdate==`function`&&(t.flags|=1024)):(typeof o.componentDidUpdate!=`function`||s===e.memoizedProps&&f===e.memoizedState||(t.flags|=4),typeof o.getSnapshotBeforeUpdate!=`function`||s===e.memoizedProps&&f===e.memoizedState||(t.flags|=1024),t.memoizedProps=r,t.memoizedState=m),o.props=r,o.state=m,o.context=c,r=l):(typeof o.componentDidUpdate!=`function`||s===e.memoizedProps&&f===e.memoizedState||(t.flags|=4),typeof o.getSnapshotBeforeUpdate!=`function`||s===e.memoizedProps&&f===e.memoizedState||(t.flags|=1024),r=!1)}return Vs(e,t,n,r,a,i)}function Vs(e,t,n,r,i,a){Rs(e,t);var o=!!(t.flags&128);if(!r&&!o)return i&&ta(t,n,!1),ec(e,t,a);r=t.stateNode,js.current=t;var s=o&&typeof n.getDerivedStateFromError!=`function`?null:r.render();return t.flags|=1,e!==null&&o?(t.child=za(t,e.child,null,a),t.child=za(t,null,s,a)):Ns(e,t,s,a),t.memoizedState=r.state,i&&ta(t,n,!0),t.child}function Hs(e){var t=e.stateNode;t.pendingContext?Qi(e,t.pendingContext,t.pendingContext!==t.context):t.context&&Qi(e,t.context,!1),ho(e,t.containerInfo)}function Us(e,t,n,r,i){return Ma(),Na(i),t.flags|=256,Ns(e,t,n,r),t.child}var Ws={dehydrated:null,treeContext:null,retryLane:0};function Gs(e){return{baseLanes:e,cachePool:null,transitions:null}}function Ks(e,t,n){var r=t.pendingProps,i=yo.current,a=!1,o=!!(t.flags&128),s;if((s=o)||(s=e!==null&&e.memoizedState===null?!1:!!(i&2)),s?(a=!0,t.flags&=-129):(e===null||e.memoizedState!==null)&&(i|=1),Wi(yo,i&1),e===null)return Oa(t),e=t.memoizedState,e!==null&&(e=e.dehydrated,e!==null)?(t.lanes=t.mode&1?e.data===`$!`?8:1073741824:1,null):(o=r.children,e=r.fallback,a?(r=t.mode,a=t.child,o={mode:`hidden`,children:o},!(r&1)&&a!==null?(a.childLanes=0,a.pendingProps=o):a=$l(o,r,0,null),e=Ql(e,r,n,null),a.return=t,e.return=t,a.sibling=e,t.child=a,t.child.memoizedState=Gs(n),t.memoizedState=Ws,e):qs(t,o));if(i=e.memoizedState,i!==null&&(s=i.dehydrated,s!==null))return Ys(e,t,o,r,s,i,n);if(a){a=r.fallback,o=t.mode,i=e.child,s=i.sibling;var c={mode:`hidden`,children:r.children};return!(o&1)&&t.child!==i?(r=t.child,r.childLanes=0,r.pendingProps=c,t.deletions=null):(r=Xl(i,c),r.subtreeFlags=i.subtreeFlags&14680064),s===null?(a=Ql(a,o,n,null),a.flags|=2):a=Xl(s,a),a.return=t,r.return=t,r.sibling=a,t.child=r,r=a,a=t.child,o=e.child.memoizedState,o=o===null?Gs(n):{baseLanes:o.baseLanes|n,cachePool:null,transitions:o.transitions},a.memoizedState=o,a.childLanes=e.childLanes&~n,t.memoizedState=Ws,r}return a=e.child,e=a.sibling,r=Xl(a,{mode:`visible`,children:r.children}),!(t.mode&1)&&(r.lanes=n),r.return=t,r.sibling=null,e!==null&&(n=t.deletions,n===null?(t.deletions=[e],t.flags|=16):n.push(e)),t.child=r,t.memoizedState=null,r}function qs(e,t){return t=$l({mode:`visible`,children:t},e.mode,0,null),t.return=e,e.child=t}function Js(e,t,n,r){return r!==null&&Na(r),za(t,e.child,null,n),e=qs(t,t.pendingProps.children),e.flags|=2,t.memoizedState=null,e}function Ys(e,t,n,i,a,o,s){if(n)return t.flags&256?(t.flags&=-257,i=Cs(Error(r(422))),Js(e,t,s,i)):t.memoizedState===null?(o=i.fallback,a=t.mode,i=$l({mode:`visible`,children:i.children},a,0,null),o=Ql(o,a,s,null),o.flags|=2,i.return=t,o.return=t,i.sibling=o,t.child=i,t.mode&1&&za(t,e.child,null,s),t.child.memoizedState=Gs(s),t.memoizedState=Ws,o):(t.child=e.child,t.flags|=128,null);if(!(t.mode&1))return Js(e,t,s,null);if(a.data===`$!`){if(i=a.nextSibling&&a.nextSibling.dataset,i)var c=i.dgst;return i=c,o=Error(r(419)),i=Cs(o,i,void 0),Js(e,t,s,i)}if(c=(s&e.childLanes)!==0,Ms||c){if(i=Hc,i!==null){switch(s&-s){case 4:a=2;break;case 16:a=8;break;case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:a=32;break;case 536870912:a=268435456;break;default:a=0}a=(a&(i.suspendedLanes|s))===0?a:0,a!==0&&a!==o.retryLane&&(o.retryLane=a,$a(e,a),hl(i,e,a,-1))}return kl(),i=Cs(Error(r(421))),Js(e,t,s,i)}return a.data===`$?`?(t.flags|=128,t.child=e.child,t=Hl.bind(null,e),a._reactRetry=t,null):(e=o.treeContext,Sa=Di(a.nextSibling),xa=t,Ca=!0,wa=null,e!==null&&(fa[pa++]=ha,fa[pa++]=ga,fa[pa++]=ma,ha=e.id,ga=e.overflow,ma=t),t=qs(t,i.children),t.flags|=4096,t)}function Xs(e,t,n){e.lanes|=t;var r=e.alternate;r!==null&&(r.lanes|=t),qa(e.return,t,n)}function Zs(e,t,n,r,i){var a=e.memoizedState;a===null?e.memoizedState={isBackwards:t,rendering:null,renderingStartTime:0,last:r,tail:n,tailMode:i}:(a.isBackwards=t,a.rendering=null,a.renderingStartTime=0,a.last=r,a.tail=n,a.tailMode=i)}function Qs(e,t,n){var r=t.pendingProps,i=r.revealOrder,a=r.tail;if(Ns(e,t,r.children,n),r=yo.current,r&2)r=r&1|2,t.flags|=128;else{if(e!==null&&e.flags&128)a:for(e=t.child;e!==null;){if(e.tag===13)e.memoizedState!==null&&Xs(e,n,t);else if(e.tag===19)Xs(e,n,t);else if(e.child!==null){e.child.return=e,e=e.child;continue}if(e===t)break a;for(;e.sibling===null;){if(e.return===null||e.return===t)break a;e=e.return}e.sibling.return=e.return,e=e.sibling}r&=1}if(Wi(yo,r),!(t.mode&1))t.memoizedState=null;else switch(i){case`forwards`:for(n=t.child,i=null;n!==null;)e=n.alternate,e!==null&&bo(e)===null&&(i=n),n=n.sibling;n=i,n===null?(i=t.child,t.child=null):(i=n.sibling,n.sibling=null),Zs(t,!1,i,n,a);break;case`backwards`:for(n=null,i=t.child,t.child=null;i!==null;){if(e=i.alternate,e!==null&&bo(e)===null){t.child=i;break}e=i.sibling,i.sibling=n,n=i,i=e}Zs(t,!0,n,null,a);break;case`together`:Zs(t,!1,null,null,void 0);break;default:t.memoizedState=null}return t.child}function $s(e,t){!(t.mode&1)&&e!==null&&(e.alternate=null,t.alternate=null,t.flags|=2)}function ec(e,t,n){if(e!==null&&(t.dependencies=e.dependencies),Yc|=t.lanes,(n&t.childLanes)===0)return null;if(e!==null&&t.child!==e.child)throw Error(r(153));if(t.child!==null){for(e=t.child,n=Xl(e,e.pendingProps),t.child=n,n.return=t;e.sibling!==null;)e=e.sibling,n=n.sibling=Xl(e,e.pendingProps),n.return=t;n.sibling=null}return t.child}function tc(e,t,n){switch(t.tag){case 3:Hs(t),Ma();break;case 5:_o(t);break;case 1:Xi(t.type)&&ea(t);break;case 4:ho(t,t.stateNode.containerInfo);break;case 10:var r=t.type._context,i=t.memoizedProps.value;Wi(Va,r._currentValue),r._currentValue=i;break;case 13:if(r=t.memoizedState,r!==null)return r.dehydrated===null?(n&t.child.childLanes)===0?(Wi(yo,yo.current&1),e=ec(e,t,n),e===null?null:e.sibling):Ks(e,t,n):(Wi(yo,yo.current&1),t.flags|=128,null);Wi(yo,yo.current&1);break;case 19:if(r=(n&t.childLanes)!==0,e.flags&128){if(r)return Qs(e,t,n);t.flags|=128}if(i=t.memoizedState,i!==null&&(i.rendering=null,i.tail=null,i.lastEffect=null),Wi(yo,yo.current),r)break;return null;case 22:case 23:return t.lanes=0,Ls(e,t,n)}return ec(e,t,n)}var nc=function(e,t){for(var n=t.child;n!==null;){if(n.tag===5||n.tag===6)e.appendChild(n.stateNode);else if(n.tag!==4&&n.child!==null){n.child.return=n,n=n.child;continue}if(n===t)break;for(;n.sibling===null;){if(n.return===null||n.return===t)return;n=n.return}n.sibling.return=n.return,n=n.sibling}},rc=function(e,t,n,r){var i=e.memoizedProps;if(i!==r){e=t.stateNode,mo(uo.current);var o=null;switch(n){case`input`:i=he(e,i),r=he(e,r),o=[];break;case`select`:i=L({},i,{value:void 0}),r=L({},r,{value:void 0}),o=[];break;case`textarea`:i=Se(e,i),r=Se(e,r),o=[];break;default:typeof i.onClick!=`function`&&typeof r.onClick==`function`&&(e.onclick=_i)}Ne(n,r);var s;for(u in n=null,i)if(!r.hasOwnProperty(u)&&i.hasOwnProperty(u)&&i[u]!=null){if(u===`style`){var c=i[u];for(s in c)c.hasOwnProperty(s)&&(n||={},n[s]=``)}else u!==`dangerouslySetInnerHTML`&&u!==`children`&&u!==`suppressContentEditableWarning`&&u!==`suppressHydrationWarning`&&u!==`autoFocus`&&(a.hasOwnProperty(u)?o||=[]:(o||=[]).push(u,null))}for(u in r){var l=r[u];if(c=i?.[u],r.hasOwnProperty(u)&&l!==c&&(l!=null||c!=null)){if(u===`style`){if(c){for(s in c)!c.hasOwnProperty(s)||l&&l.hasOwnProperty(s)||(n||={},n[s]=``);for(s in l)l.hasOwnProperty(s)&&c[s]!==l[s]&&(n||={},n[s]=l[s])}else n||(o||=[],o.push(u,n)),n=l}else u===`dangerouslySetInnerHTML`?(l=l?l.__html:void 0,c=c?c.__html:void 0,l!=null&&c!==l&&(o||=[]).push(u,l)):u===`children`?typeof l!=`string`&&typeof l!=`number`||(o||=[]).push(u,``+l):u!==`suppressContentEditableWarning`&&u!==`suppressHydrationWarning`&&(a.hasOwnProperty(u)?(l!=null&&u===`onScroll`&&ri(`scroll`,e),o||c===l||(o=[])):(o||=[]).push(u,l))}}n&&(o||=[]).push(`style`,n);var u=o;(t.updateQueue=u)&&(t.flags|=4)}},ic=function(e,t,n,r){n!==r&&(t.flags|=4)};function ac(e,t){if(!Ca)switch(e.tailMode){case`hidden`:t=e.tail;for(var n=null;t!==null;)t.alternate!==null&&(n=t),t=t.sibling;n===null?e.tail=null:n.sibling=null;break;case`collapsed`:n=e.tail;for(var r=null;n!==null;)n.alternate!==null&&(r=n),n=n.sibling;r===null?t||e.tail===null?e.tail=null:e.tail.sibling=null:r.sibling=null}}function oc(e){var t=e.alternate!==null&&e.alternate.child===e.child,n=0,r=0;if(t)for(var i=e.child;i!==null;)n|=i.lanes|i.childLanes,r|=i.subtreeFlags&14680064,r|=i.flags&14680064,i.return=e,i=i.sibling;else for(i=e.child;i!==null;)n|=i.lanes|i.childLanes,r|=i.subtreeFlags,r|=i.flags,i.return=e,i=i.sibling;return e.subtreeFlags|=r,e.childLanes=n,t}function sc(e,t,n){var i=t.pendingProps;switch(ba(t),t.tag){case 2:case 16:case 15:case 0:case 11:case 7:case 8:case 12:case 9:case 14:return oc(t),null;case 1:return Xi(t.type)&&Zi(),oc(t),null;case 3:return i=t.stateNode,go(),Ui(qi),Ui(Ki),So(),i.pendingContext&&(i.context=i.pendingContext,i.pendingContext=null),(e===null||e.child===null)&&(Aa(t)?t.flags|=4:e===null||e.memoizedState.isDehydrated&&!(t.flags&256)||(t.flags|=1024,wa!==null&&(yl(wa),wa=null))),oc(t),null;case 5:vo(t);var o=mo(po.current);if(n=t.type,e!==null&&t.stateNode!=null)rc(e,t,n,i,o),e.ref!==t.ref&&(t.flags|=512,t.flags|=2097152);else{if(!i){if(t.stateNode===null)throw Error(r(166));return oc(t),null}if(e=mo(uo.current),Aa(t)){i=t.stateNode,n=t.type;var s=t.memoizedProps;switch(i[Ai]=t,i[ji]=s,e=!!(t.mode&1),n){case`dialog`:ri(`cancel`,i),ri(`close`,i);break;case`iframe`:case`object`:case`embed`:ri(`load`,i);break;case`video`:case`audio`:for(o=0;o<$r.length;o++)ri($r[o],i);break;case`source`:ri(`error`,i);break;case`img`:case`image`:case`link`:ri(`error`,i),ri(`load`,i);break;case`details`:ri(`toggle`,i);break;case`input`:ge(i,s),ri(`invalid`,i);break;case`select`:i._wrapperState={wasMultiple:!!s.multiple},ri(`invalid`,i);break;case`textarea`:z(i,s),ri(`invalid`,i)}for(var c in Ne(n,s),o=null,s)if(s.hasOwnProperty(c)){var l=s[c];c===`children`?typeof l==`string`?i.textContent!==l&&(!0!==s.suppressHydrationWarning&&gi(i.textContent,l,e),o=[`children`,l]):typeof l==`number`&&i.textContent!==``+l&&(!0!==s.suppressHydrationWarning&&gi(i.textContent,l,e),o=[`children`,``+l]):a.hasOwnProperty(c)&&l!=null&&c===`onScroll`&&ri(`scroll`,i)}switch(n){case`input`:fe(i),ye(i,s,!0);break;case`textarea`:fe(i),B(i);break;case`select`:case`option`:break;default:typeof s.onClick==`function`&&(i.onclick=_i)}i=o,t.updateQueue=i,i!==null&&(t.flags|=4)}else{c=o.nodeType===9?o:o.ownerDocument,e===`http://www.w3.org/1999/xhtml`&&(e=V(n)),e===`http://www.w3.org/1999/xhtml`?n===`script`?(e=c.createElement(`div`),e.innerHTML=`<script><\/script>`,e=e.removeChild(e.firstChild)):typeof i.is==`string`?e=c.createElement(n,{is:i.is}):(e=c.createElement(n),n===`select`&&(c=e,i.multiple?c.multiple=!0:i.size&&(c.size=i.size))):e=c.createElementNS(e,n),e[Ai]=t,e[ji]=i,nc(e,t,!1,!1),t.stateNode=e;a:{switch(c=Pe(n,i),n){case`dialog`:ri(`cancel`,e),ri(`close`,e),o=i;break;case`iframe`:case`object`:case`embed`:ri(`load`,e),o=i;break;case`video`:case`audio`:for(o=0;o<$r.length;o++)ri($r[o],e);o=i;break;case`source`:ri(`error`,e),o=i;break;case`img`:case`image`:case`link`:ri(`error`,e),ri(`load`,e),o=i;break;case`details`:ri(`toggle`,e),o=i;break;case`input`:ge(e,i),o=he(e,i),ri(`invalid`,e);break;case`option`:o=i;break;case`select`:e._wrapperState={wasMultiple:!!i.multiple},o=L({},i,{value:void 0}),ri(`invalid`,e);break;case`textarea`:z(e,i),o=Se(e,i),ri(`invalid`,e);break;default:o=i}for(s in Ne(n,o),l=o,l)if(l.hasOwnProperty(s)){var u=l[s];s===`style`?je(e,u):s===`dangerouslySetInnerHTML`?(u=u?u.__html:void 0,u!=null&&Ee(e,u)):s===`children`?typeof u==`string`?(n!==`textarea`||u!==``)&&De(e,u):typeof u==`number`&&De(e,``+u):s!==`suppressContentEditableWarning`&&s!==`suppressHydrationWarning`&&s!==`autoFocus`&&(a.hasOwnProperty(s)?u!=null&&s===`onScroll`&&ri(`scroll`,e):u!=null&&S(e,s,u,c))}switch(n){case`input`:fe(e),ye(e,i,!1);break;case`textarea`:fe(e),B(e);break;case`option`:i.value!=null&&e.setAttribute(`value`,``+le(i.value));break;case`select`:e.multiple=!!i.multiple,s=i.value,s==null?i.defaultValue!=null&&xe(e,!!i.multiple,i.defaultValue,!0):xe(e,!!i.multiple,s,!1);break;default:typeof o.onClick==`function`&&(e.onclick=_i)}switch(n){case`button`:case`input`:case`select`:case`textarea`:i=!!i.autoFocus;break a;case`img`:i=!0;break a;default:i=!1}}i&&(t.flags|=4)}t.ref!==null&&(t.flags|=512,t.flags|=2097152)}return oc(t),null;case 6:if(e&&t.stateNode!=null)ic(e,t,e.memoizedProps,i);else{if(typeof i!=`string`&&t.stateNode===null)throw Error(r(166));if(n=mo(po.current),mo(uo.current),Aa(t)){if(i=t.stateNode,n=t.memoizedProps,i[Ai]=t,(s=i.nodeValue!==n)&&(e=xa,e!==null))switch(e.tag){case 3:gi(i.nodeValue,n,!!(e.mode&1));break;case 5:!0!==e.memoizedProps.suppressHydrationWarning&&gi(i.nodeValue,n,!!(e.mode&1))}s&&(t.flags|=4)}else i=(n.nodeType===9?n:n.ownerDocument).createTextNode(i),i[Ai]=t,t.stateNode=i}return oc(t),null;case 13:if(Ui(yo),i=t.memoizedState,e===null||e.memoizedState!==null&&e.memoizedState.dehydrated!==null){if(Ca&&Sa!==null&&t.mode&1&&!(t.flags&128))ja(),Ma(),t.flags|=98560,s=!1;else if(s=Aa(t),i!==null&&i.dehydrated!==null){if(e===null){if(!s)throw Error(r(318));if(s=t.memoizedState,s=s===null?null:s.dehydrated,!s)throw Error(r(317));s[Ai]=t}else Ma(),!(t.flags&128)&&(t.memoizedState=null),t.flags|=4;oc(t),s=!1}else wa!==null&&(yl(wa),wa=null),s=!0;if(!s)return t.flags&65536?t:null}return t.flags&128?(t.lanes=n,t):(i=i!==null,i!==(e!==null&&e.memoizedState!==null)&&i&&(t.child.flags|=8192,t.mode&1&&(e===null||yo.current&1?qc===0&&(qc=3):kl())),t.updateQueue!==null&&(t.flags|=4),oc(t),null);case 4:return go(),e===null&&oi(t.stateNode.containerInfo),oc(t),null;case 10:return Ka(t.type._context),oc(t),null;case 17:return Xi(t.type)&&Zi(),oc(t),null;case 19:if(Ui(yo),s=t.memoizedState,s===null)return oc(t),null;if(i=!!(t.flags&128),c=s.rendering,c===null){if(i)ac(s,!1);else{if(qc!==0||e!==null&&e.flags&128)for(e=t.child;e!==null;){if(c=bo(e),c!==null){for(t.flags|=128,ac(s,!1),i=c.updateQueue,i!==null&&(t.updateQueue=i,t.flags|=4),t.subtreeFlags=0,i=n,n=t.child;n!==null;)s=n,e=i,s.flags&=14680066,c=s.alternate,c===null?(s.childLanes=0,s.lanes=e,s.child=null,s.subtreeFlags=0,s.memoizedProps=null,s.memoizedState=null,s.updateQueue=null,s.dependencies=null,s.stateNode=null):(s.childLanes=c.childLanes,s.lanes=c.lanes,s.child=c.child,s.subtreeFlags=0,s.deletions=null,s.memoizedProps=c.memoizedProps,s.memoizedState=c.memoizedState,s.updateQueue=c.updateQueue,s.type=c.type,e=c.dependencies,s.dependencies=e===null?null:{lanes:e.lanes,firstContext:e.firstContext}),n=n.sibling;return Wi(yo,yo.current&1|2),t.child}e=e.sibling}s.tail!==null&&mt()>tl&&(t.flags|=128,i=!0,ac(s,!1),t.lanes=4194304)}}else{if(!i){if(e=bo(c),e!==null){if(t.flags|=128,i=!0,n=e.updateQueue,n!==null&&(t.updateQueue=n,t.flags|=4),ac(s,!0),s.tail===null&&s.tailMode===`hidden`&&!c.alternate&&!Ca)return oc(t),null}else 2*mt()-s.renderingStartTime>tl&&n!==1073741824&&(t.flags|=128,i=!0,ac(s,!1),t.lanes=4194304)}s.isBackwards?(c.sibling=t.child,t.child=c):(n=s.last,n===null?t.child=c:n.sibling=c,s.last=c)}return s.tail===null?(oc(t),null):(t=s.tail,s.rendering=t,s.tail=t.sibling,s.renderingStartTime=mt(),t.sibling=null,n=yo.current,Wi(yo,i?n&1|2:n&1),t);case 22:case 23:return Tl(),i=t.memoizedState!==null,e!==null&&e.memoizedState!==null!==i&&(t.flags|=8192),i&&t.mode&1?Gc&1073741824&&(oc(t),t.subtreeFlags&6&&(t.flags|=8192)):oc(t),null;case 24:return null;case 25:return null}throw Error(r(156,t.tag))}function cc(e,t){switch(ba(t),t.tag){case 1:return Xi(t.type)&&Zi(),e=t.flags,e&65536?(t.flags=e&-65537|128,t):null;case 3:return go(),Ui(qi),Ui(Ki),So(),e=t.flags,e&65536&&!(e&128)?(t.flags=e&-65537|128,t):null;case 5:return vo(t),null;case 13:if(Ui(yo),e=t.memoizedState,e!==null&&e.dehydrated!==null){if(t.alternate===null)throw Error(r(340));Ma()}return e=t.flags,e&65536?(t.flags=e&-65537|128,t):null;case 19:return Ui(yo),null;case 4:return go(),null;case 10:return Ka(t.type._context),null;case 22:case 23:return Tl(),null;case 24:return null;default:return null}}var lc=!1,uc=!1,dc=typeof WeakSet==`function`?WeakSet:Set,Q=null;function fc(e,t){var n=e.ref;if(n!==null){if(typeof n==`function`)try{n(null)}catch(n){zl(e,t,n)}else n.current=null}}function pc(e,t,n){try{n()}catch(n){zl(e,t,n)}}var mc=!1;function hc(e,t){if(vi=fn,e=Ar(),jr(e)){if(`selectionStart`in e)var n={start:e.selectionStart,end:e.selectionEnd};else a:{n=(n=e.ownerDocument)&&n.defaultView||window;var i=n.getSelection&&n.getSelection();if(i&&i.rangeCount!==0){n=i.anchorNode;var a=i.anchorOffset,o=i.focusNode;i=i.focusOffset;try{n.nodeType,o.nodeType}catch{n=null;break a}var s=0,c=-1,l=-1,u=0,d=0,f=e,p=null;b:for(;;){for(var m;f!==n||a!==0&&f.nodeType!==3||(c=s+a),f!==o||i!==0&&f.nodeType!==3||(l=s+i),f.nodeType===3&&(s+=f.nodeValue.length),(m=f.firstChild)!==null;)p=f,f=m;for(;;){if(f===e)break b;if(p===n&&++u===a&&(c=s),p===o&&++d===i&&(l=s),(m=f.nextSibling)!==null)break;f=p,p=f.parentNode}f=m}n=c===-1||l===-1?null:{start:c,end:l}}else n=null}n||={start:0,end:0}}else n=null;for(yi={focusedElem:e,selectionRange:n},fn=!1,Q=t;Q!==null;)if(t=Q,e=t.child,t.subtreeFlags&1028&&e!==null)e.return=t,Q=e;else for(;Q!==null;){t=Q;try{var h=t.alternate;if(t.flags&1024)switch(t.tag){case 0:case 11:case 15:break;case 1:if(h!==null){var g=h.memoizedProps,_=h.memoizedState,v=t.stateNode;v.__reactInternalSnapshotBeforeUpdate=v.getSnapshotBeforeUpdate(t.elementType===t.type?g:hs(t.type,g),_)}break;case 3:var y=t.stateNode.containerInfo;y.nodeType===1?y.textContent=``:y.nodeType===9&&y.documentElement&&y.removeChild(y.documentElement);break;case 5:case 6:case 4:case 17:break;default:throw Error(r(163))}}catch(e){zl(t,t.return,e)}if(e=t.sibling,e!==null){e.return=t.return,Q=e;break}Q=t.return}return h=mc,mc=!1,h}function gc(e,t,n){var r=t.updateQueue;if(r=r===null?null:r.lastEffect,r!==null){var i=r=r.next;do{if((i.tag&e)===e){var a=i.destroy;i.destroy=void 0,a!==void 0&&pc(t,n,a)}i=i.next}while(i!==r)}}function _c(e,t){if(t=t.updateQueue,t=t===null?null:t.lastEffect,t!==null){var n=t=t.next;do{if((n.tag&e)===e){var r=n.create;n.destroy=r()}n=n.next}while(n!==t)}}function vc(e){var t=e.ref;if(t!==null){var n=e.stateNode;switch(e.tag){case 5:e=n;break;default:e=n}typeof t==`function`?t(e):t.current=e}}function yc(e){var t=e.alternate;t!==null&&(e.alternate=null,yc(t)),e.child=null,e.deletions=null,e.sibling=null,e.tag===5&&(t=e.stateNode,t!==null&&(delete t[Ai],delete t[ji],delete t[Ni],delete t[Pi],delete t[Fi])),e.stateNode=null,e.return=null,e.dependencies=null,e.memoizedProps=null,e.memoizedState=null,e.pendingProps=null,e.stateNode=null,e.updateQueue=null}function bc(e){return e.tag===5||e.tag===3||e.tag===4}function xc(e){a:for(;;){for(;e.sibling===null;){if(e.return===null||bc(e.return))return null;e=e.return}for(e.sibling.return=e.return,e=e.sibling;e.tag!==5&&e.tag!==6&&e.tag!==18;){if(e.flags&2||e.child===null||e.tag===4)continue a;e.child.return=e,e=e.child}if(!(e.flags&2))return e.stateNode}}function Sc(e,t,n){var r=e.tag;if(r===5||r===6)e=e.stateNode,t?n.nodeType===8?n.parentNode.insertBefore(e,t):n.insertBefore(e,t):(n.nodeType===8?(t=n.parentNode,t.insertBefore(e,n)):(t=n,t.appendChild(e)),n=n._reactRootContainer,n!=null||t.onclick!==null||(t.onclick=_i));else if(r!==4&&(e=e.child,e!==null))for(Sc(e,t,n),e=e.sibling;e!==null;)Sc(e,t,n),e=e.sibling}function Cc(e,t,n){var r=e.tag;if(r===5||r===6)e=e.stateNode,t?n.insertBefore(e,t):n.appendChild(e);else if(r!==4&&(e=e.child,e!==null))for(Cc(e,t,n),e=e.sibling;e!==null;)Cc(e,t,n),e=e.sibling}var wc=null,Tc=!1;function Ec(e,t,n){for(n=n.child;n!==null;)Dc(e,t,n),n=n.sibling}function Dc(e,t,n){if(St&&typeof St.onCommitFiberUnmount==`function`)try{St.onCommitFiberUnmount(xt,n)}catch{}switch(n.tag){case 5:uc||fc(n,t);case 6:var r=wc,i=Tc;wc=null,Ec(e,t,n),wc=r,Tc=i,wc!==null&&(Tc?(e=wc,n=n.stateNode,e.nodeType===8?e.parentNode.removeChild(n):e.removeChild(n)):wc.removeChild(n.stateNode));break;case 18:wc!==null&&(Tc?(e=wc,n=n.stateNode,e.nodeType===8?Ei(e.parentNode,n):e.nodeType===1&&Ei(e,n),un(e)):Ei(wc,n.stateNode));break;case 4:r=wc,i=Tc,wc=n.stateNode.containerInfo,Tc=!0,Ec(e,t,n),wc=r,Tc=i;break;case 0:case 11:case 14:case 15:if(!uc&&(r=n.updateQueue,r!==null&&(r=r.lastEffect,r!==null))){i=r=r.next;do{var a=i,o=a.destroy;a=a.tag,o!==void 0&&(a&2||a&4)&&pc(n,t,o),i=i.next}while(i!==r)}Ec(e,t,n);break;case 1:if(!uc&&(fc(n,t),r=n.stateNode,typeof r.componentWillUnmount==`function`))try{r.props=n.memoizedProps,r.state=n.memoizedState,r.componentWillUnmount()}catch(e){zl(n,t,e)}Ec(e,t,n);break;case 21:Ec(e,t,n);break;case 22:n.mode&1?(uc=(r=uc)||n.memoizedState!==null,Ec(e,t,n),uc=r):Ec(e,t,n);break;default:Ec(e,t,n)}}function Oc(e){var t=e.updateQueue;if(t!==null){e.updateQueue=null;var n=e.stateNode;n===null&&(n=e.stateNode=new dc),t.forEach(function(t){var r=Ul.bind(null,e,t);n.has(t)||(n.add(t),t.then(r,r))})}}function kc(e,t){var n=t.deletions;if(n!==null)for(var i=0;i<n.length;i++){var a=n[i];try{var o=e,s=t,c=s;a:for(;c!==null;){switch(c.tag){case 5:wc=c.stateNode,Tc=!1;break a;case 3:wc=c.stateNode.containerInfo,Tc=!0;break a;case 4:wc=c.stateNode.containerInfo,Tc=!0;break a}c=c.return}if(wc===null)throw Error(r(160));Dc(o,s,a),wc=null,Tc=!1;var l=a.alternate;l!==null&&(l.return=null),a.return=null}catch(e){zl(a,t,e)}}if(t.subtreeFlags&12854)for(t=t.child;t!==null;)Ac(t,e),t=t.sibling}function Ac(e,t){var n=e.alternate,i=e.flags;switch(e.tag){case 0:case 11:case 14:case 15:if(kc(t,e),jc(e),i&4){try{gc(3,e,e.return),_c(3,e)}catch(t){zl(e,e.return,t)}try{gc(5,e,e.return)}catch(t){zl(e,e.return,t)}}break;case 1:kc(t,e),jc(e),i&512&&n!==null&&fc(n,n.return);break;case 5:if(kc(t,e),jc(e),i&512&&n!==null&&fc(n,n.return),e.flags&32){var a=e.stateNode;try{De(a,``)}catch(t){zl(e,e.return,t)}}if(i&4&&(a=e.stateNode,a!=null)){var o=e.memoizedProps,s=n===null?o:n.memoizedProps,c=e.type,l=e.updateQueue;if(e.updateQueue=null,l!==null)try{c===`input`&&o.type===`radio`&&o.name!=null&&_e(a,o),Pe(c,s);var u=Pe(c,o);for(s=0;s<l.length;s+=2){var d=l[s],f=l[s+1];d===`style`?je(a,f):d===`dangerouslySetInnerHTML`?Ee(a,f):d===`children`?De(a,f):S(a,d,f,u)}switch(c){case`input`:ve(a,o);break;case`textarea`:Ce(a,o);break;case`select`:var p=a._wrapperState.wasMultiple;a._wrapperState.wasMultiple=!!o.multiple;var m=o.value;m==null?p!==!!o.multiple&&(o.defaultValue==null?xe(a,!!o.multiple,o.multiple?[]:``,!1):xe(a,!!o.multiple,o.defaultValue,!0)):xe(a,!!o.multiple,m,!1)}a[ji]=o}catch(t){zl(e,e.return,t)}}break;case 6:if(kc(t,e),jc(e),i&4){if(e.stateNode===null)throw Error(r(162));a=e.stateNode,o=e.memoizedProps;try{a.nodeValue=o}catch(t){zl(e,e.return,t)}}break;case 3:if(kc(t,e),jc(e),i&4&&n!==null&&n.memoizedState.isDehydrated)try{un(t.containerInfo)}catch(t){zl(e,e.return,t)}break;case 4:kc(t,e),jc(e);break;case 13:kc(t,e),jc(e),a=e.child,a.flags&8192&&(o=a.memoizedState!==null,a.stateNode.isHidden=o,!o||a.alternate!==null&&a.alternate.memoizedState!==null||(el=mt())),i&4&&Oc(e);break;case 22:if(d=n!==null&&n.memoizedState!==null,e.mode&1?(uc=(u=uc)||d,kc(t,e),uc=u):kc(t,e),jc(e),i&8192){if(u=e.memoizedState!==null,(e.stateNode.isHidden=u)&&!d&&e.mode&1)for(Q=e,d=e.child;d!==null;){for(f=Q=d;Q!==null;){switch(p=Q,m=p.child,p.tag){case 0:case 11:case 14:case 15:gc(4,p,p.return);break;case 1:fc(p,p.return);var h=p.stateNode;if(typeof h.componentWillUnmount==`function`){i=p,n=p.return;try{t=i,h.props=t.memoizedProps,h.state=t.memoizedState,h.componentWillUnmount()}catch(e){zl(i,n,e)}}break;case 5:fc(p,p.return);break;case 22:if(p.memoizedState!==null){Fc(f);continue}}m===null?Fc(f):(m.return=p,Q=m)}d=d.sibling}a:for(d=null,f=e;;){if(f.tag===5){if(d===null){d=f;try{a=f.stateNode,u?(o=a.style,typeof o.setProperty==`function`?o.setProperty(`display`,`none`,`important`):o.display=`none`):(c=f.stateNode,l=f.memoizedProps.style,s=l!=null&&l.hasOwnProperty(`display`)?l.display:null,c.style.display=Ae(`display`,s))}catch(t){zl(e,e.return,t)}}}else if(f.tag===6){if(d===null)try{f.stateNode.nodeValue=u?``:f.memoizedProps}catch(t){zl(e,e.return,t)}}else if((f.tag!==22&&f.tag!==23||f.memoizedState===null||f===e)&&f.child!==null){f.child.return=f,f=f.child;continue}if(f===e)break a;for(;f.sibling===null;){if(f.return===null||f.return===e)break a;d===f&&(d=null),f=f.return}d===f&&(d=null),f.sibling.return=f.return,f=f.sibling}}break;case 19:kc(t,e),jc(e),i&4&&Oc(e);break;case 21:break;default:kc(t,e),jc(e)}}function jc(e){var t=e.flags;if(t&2){try{a:{for(var n=e.return;n!==null;){if(bc(n)){var i=n;break a}n=n.return}throw Error(r(160))}switch(i.tag){case 5:var a=i.stateNode;i.flags&32&&(De(a,``),i.flags&=-33),Cc(e,xc(e),a);break;case 3:case 4:var o=i.stateNode.containerInfo;Sc(e,xc(e),o);break;default:throw Error(r(161))}}catch(t){zl(e,e.return,t)}e.flags&=-3}t&4096&&(e.flags&=-4097)}function Mc(e,t,n){Q=e,Nc(e,t,n)}function Nc(e,t,n){for(var r=!!(e.mode&1);Q!==null;){var i=Q,a=i.child;if(i.tag===22&&r){var o=i.memoizedState!==null||lc;if(!o){var s=i.alternate,c=s!==null&&s.memoizedState!==null||uc;s=lc;var l=uc;if(lc=o,(uc=c)&&!l)for(Q=i;Q!==null;)o=Q,c=o.child,o.tag===22&&o.memoizedState!==null||c===null?Ic(i):(c.return=o,Q=c);for(;a!==null;)Q=a,Nc(a,t,n),a=a.sibling;Q=i,lc=s,uc=l}Pc(e,t,n)}else i.subtreeFlags&8772&&a!==null?(a.return=i,Q=a):Pc(e,t,n)}}function Pc(e){for(;Q!==null;){var t=Q;if(t.flags&8772){var n=t.alternate;try{if(t.flags&8772)switch(t.tag){case 0:case 11:case 15:uc||_c(5,t);break;case 1:var i=t.stateNode;if(t.flags&4&&!uc){if(n===null)i.componentDidMount();else{var a=t.elementType===t.type?n.memoizedProps:hs(t.type,n.memoizedProps);i.componentDidUpdate(a,n.memoizedState,i.__reactInternalSnapshotBeforeUpdate)}}var o=t.updateQueue;o!==null&&co(t,o,i);break;case 3:var s=t.updateQueue;if(s!==null){if(n=null,t.child!==null)switch(t.child.tag){case 5:n=t.child.stateNode;break;case 1:n=t.child.stateNode}co(t,s,n)}break;case 5:var c=t.stateNode;if(n===null&&t.flags&4){n=c;var l=t.memoizedProps;switch(t.type){case`button`:case`input`:case`select`:case`textarea`:l.autoFocus&&n.focus();break;case`img`:l.src&&(n.src=l.src)}}break;case 6:break;case 4:break;case 12:break;case 13:if(t.memoizedState===null){var u=t.alternate;if(u!==null){var d=u.memoizedState;if(d!==null){var f=d.dehydrated;f!==null&&un(f)}}}break;case 19:case 17:case 21:case 22:case 23:case 25:break;default:throw Error(r(163))}uc||t.flags&512&&vc(t)}catch(e){zl(t,t.return,e)}}if(t===e){Q=null;break}if(n=t.sibling,n!==null){n.return=t.return,Q=n;break}Q=t.return}}function Fc(e){for(;Q!==null;){var t=Q;if(t===e){Q=null;break}var n=t.sibling;if(n!==null){n.return=t.return,Q=n;break}Q=t.return}}function Ic(e){for(;Q!==null;){var t=Q;try{switch(t.tag){case 0:case 11:case 15:var n=t.return;try{_c(4,t)}catch(e){zl(t,n,e)}break;case 1:var r=t.stateNode;if(typeof r.componentDidMount==`function`){var i=t.return;try{r.componentDidMount()}catch(e){zl(t,i,e)}}var a=t.return;try{vc(t)}catch(e){zl(t,a,e)}break;case 5:var o=t.return;try{vc(t)}catch(e){zl(t,o,e)}}}catch(e){zl(t,t.return,e)}if(t===e){Q=null;break}var s=t.sibling;if(s!==null){s.return=t.return,Q=s;break}Q=t.return}}var Lc=Math.ceil,Rc=C.ReactCurrentDispatcher,zc=C.ReactCurrentOwner,Bc=C.ReactCurrentBatchConfig,Vc=0,Hc=null,Uc=null,Wc=0,Gc=0,Kc=Hi(0),qc=0,Jc=null,Yc=0,Xc=0,Zc=0,Qc=null,$c=null,el=0,tl=1/0,nl=null,rl=!1,il=null,al=null,ol=!1,sl=null,cl=0,ll=0,ul=null,dl=-1,fl=0;function pl(){return Vc&6?mt():dl===-1?dl=mt():dl}function ml(e){return e.mode&1?Vc&2&&Wc!==0?Wc&-Wc:Pa.transition===null?(e=zt,e===0?(e=window.event,e=e===void 0?16:vn(e.type),e):e):(fl===0&&(fl=Pt()),fl):1}function hl(e,t,n,i){if(50<ll)throw ll=0,ul=null,Error(r(185));It(e,n,i),(!(Vc&2)||e!==Hc)&&(e===Hc&&(!(Vc&2)&&(Xc|=n),qc===4&&xl(e,Wc)),gl(e,i),n===1&&Vc===0&&!(t.mode&1)&&(tl=mt()+500,ra&&sa()))}function gl(e,t){var n=e.callbackNode;Mt(e,t);var r=H(e,e===Hc?Wc:0);if(r===0)n!==null&&dt(n),e.callbackNode=null,e.callbackPriority=0;else if(t=r&-r,e.callbackPriority!==t){if(n!=null&&dt(n),t===1)e.tag===0?oa(Sl.bind(null,e)):aa(Sl.bind(null,e)),wi(function(){!(Vc&6)&&sa()}),n=null;else{switch(Bt(r)){case 1:n=gt;break;case 4:n=_t;break;case 16:n=vt;break;case 536870912:n=bt;break;default:n=vt}n=Gl(n,_l.bind(null,e))}e.callbackPriority=t,e.callbackNode=n}}function _l(e,t){if(dl=-1,fl=0,Vc&6)throw Error(r(327));var n=e.callbackNode;if(Ll()&&e.callbackNode!==n)return null;var i=H(e,e===Hc?Wc:0);if(i===0)return null;if(i&30||(i&e.expiredLanes)!==0||t)t=Al(e,i);else{t=i;var a=Vc;Vc|=2;var o=Ol();(Hc!==e||Wc!==t)&&(nl=null,tl=mt()+500,El(e,t));do try{Ml();break}catch(t){Dl(e,t)}while(1);Ga(),Rc.current=o,Vc=a,Uc===null?(Hc=null,Wc=0,t=qc):t=0}if(t!==0){if(t===2&&(a=Nt(e),a!==0&&(i=a,t=vl(e,a))),t===1)throw n=Jc,El(e,0),xl(e,i),gl(e,mt()),n;if(t===6)xl(e,i);else{if(a=e.current.alternate,!(i&30)&&!bl(a)&&(t=Al(e,i),t===2&&(o=Nt(e),o!==0&&(i=o,t=vl(e,o))),t===1))throw n=Jc,El(e,0),xl(e,i),gl(e,mt()),n;switch(e.finishedWork=a,e.finishedLanes=i,t){case 0:case 1:throw Error(r(345));case 2:Fl(e,$c,nl);break;case 3:if(xl(e,i),(i&130023424)===i&&(t=el+500-mt(),10<t)){if(H(e,0)!==0)break;if(a=e.suspendedLanes,(a&i)!==i){pl(),e.pingedLanes|=e.suspendedLanes&a;break}e.timeoutHandle=xi(Fl.bind(null,e,$c,nl),t);break}Fl(e,$c,nl);break;case 4:if(xl(e,i),(i&4194240)===i)break;for(t=e.eventTimes,a=-1;0<i;){var s=31-wt(i);o=1<<s,s=t[s],s>a&&(a=s),i&=~o}if(i=a,i=mt()-i,i=(120>i?120:480>i?480:1080>i?1080:1920>i?1920:3e3>i?3e3:4320>i?4320:1960*Lc(i/1960))-i,10<i){e.timeoutHandle=xi(Fl.bind(null,e,$c,nl),i);break}Fl(e,$c,nl);break;case 5:Fl(e,$c,nl);break;default:throw Error(r(329))}}}return gl(e,mt()),e.callbackNode===n?_l.bind(null,e):null}function vl(e,t){var n=Qc;return e.current.memoizedState.isDehydrated&&(El(e,t).flags|=256),e=Al(e,t),e!==2&&(t=$c,$c=n,t!==null&&yl(t)),e}function yl(e){$c===null?$c=e:$c.push.apply($c,e)}function bl(e){for(var t=e;;){if(t.flags&16384){var n=t.updateQueue;if(n!==null&&(n=n.stores,n!==null))for(var r=0;r<n.length;r++){var i=n[r],a=i.getSnapshot;i=i.value;try{if(!Tr(a(),i))return!1}catch{return!1}}}if(n=t.child,t.subtreeFlags&16384&&n!==null)n.return=t,t=n;else{if(t===e)break;for(;t.sibling===null;){if(t.return===null||t.return===e)return!0;t=t.return}t.sibling.return=t.return,t=t.sibling}}return!0}function xl(e,t){for(t&=~Zc,t&=~Xc,e.suspendedLanes|=t,e.pingedLanes&=~t,e=e.expirationTimes;0<t;){var n=31-wt(t),r=1<<n;e[n]=-1,t&=~r}}function Sl(e){if(Vc&6)throw Error(r(327));Ll();var t=H(e,0);if(!(t&1))return gl(e,mt()),null;var n=Al(e,t);if(e.tag!==0&&n===2){var i=Nt(e);i!==0&&(t=i,n=vl(e,i))}if(n===1)throw n=Jc,El(e,0),xl(e,t),gl(e,mt()),n;if(n===6)throw Error(r(345));return e.finishedWork=e.current.alternate,e.finishedLanes=t,Fl(e,$c,nl),gl(e,mt()),null}function Cl(e,t){var n=Vc;Vc|=1;try{return e(t)}finally{Vc=n,Vc===0&&(tl=mt()+500,ra&&sa())}}function wl(e){sl!==null&&sl.tag===0&&!(Vc&6)&&Ll();var t=Vc;Vc|=1;var n=Bc.transition,r=zt;try{if(Bc.transition=null,zt=1,e)return e()}finally{zt=r,Bc.transition=n,Vc=t,!(Vc&6)&&sa()}}function Tl(){Gc=Kc.current,Ui(Kc)}function El(e,t){e.finishedWork=null,e.finishedLanes=0;var n=e.timeoutHandle;if(n!==-1&&(e.timeoutHandle=-1,Si(n)),Uc!==null)for(n=Uc.return;n!==null;){var r=n;switch(ba(r),r.tag){case 1:r=r.type.childContextTypes,r!=null&&Zi();break;case 3:go(),Ui(qi),Ui(Ki),So();break;case 5:vo(r);break;case 4:go();break;case 13:Ui(yo);break;case 19:Ui(yo);break;case 10:Ka(r.type._context);break;case 22:case 23:Tl()}n=n.return}if(Hc=e,Uc=e=Xl(e.current,null),Wc=Gc=t,qc=0,Jc=null,Zc=Xc=Yc=0,$c=Qc=null,Xa!==null){for(t=0;t<Xa.length;t++)if(n=Xa[t],r=n.interleaved,r!==null){n.interleaved=null;var i=r.next,a=n.pending;if(a!==null){var o=a.next;a.next=i,r.next=o}n.pending=r}Xa=null}return e}function Dl(e,t){do{var n=Uc;try{if(Ga(),Co.current=fs,ko){for(var i=Eo.memoizedState;i!==null;){var a=i.queue;a!==null&&(a.pending=null),i=i.next}ko=!1}if(To=0,Oo=Do=Eo=null,Ao=!1,jo=0,zc.current=null,n===null||n.return===null){qc=1,Jc=t,Uc=null;break}a:{var o=e,s=n.return,c=n,l=t;if(t=Wc,c.flags|=32768,typeof l==`object`&&l&&typeof l.then==`function`){var u=l,d=c,f=d.tag;if(!(d.mode&1)&&(f===0||f===11||f===15)){var p=d.alternate;p?(d.updateQueue=p.updateQueue,d.memoizedState=p.memoizedState,d.lanes=p.lanes):(d.updateQueue=null,d.memoizedState=null)}var m=ks(s);if(m!==null){m.flags&=-257,As(m,s,c,o,t),m.mode&1&&Os(o,u,t),t=m,l=u;var h=t.updateQueue;if(h===null){var g=new Set;g.add(l),t.updateQueue=g}else h.add(l);break a}if(!(t&1)){Os(o,u,t),kl();break a}l=Error(r(426))}else if(Ca&&c.mode&1){var _=ks(s);if(_!==null){!(_.flags&65536)&&(_.flags|=256),As(_,s,c,o,t),Na(Ss(l,c));break a}}o=l=Ss(l,c),qc!==4&&(qc=2),Qc===null?Qc=[o]:Qc.push(o),o=s;do{switch(o.tag){case 3:o.flags|=65536,t&=-t,o.lanes|=t;var v=Es(o,l,t);oo(o,v);break a;case 1:c=l;var y=o.type,b=o.stateNode;if(!(o.flags&128)&&(typeof y.getDerivedStateFromError==`function`||b!==null&&typeof b.componentDidCatch==`function`&&(al===null||!al.has(b)))){o.flags|=65536,t&=-t,o.lanes|=t;var x=Ds(o,c,t);oo(o,x);break a}}o=o.return}while(o!==null)}Pl(n)}catch(e){t=e,Uc===n&&n!==null&&(Uc=n=n.return);continue}break}while(1)}function Ol(){var e=Rc.current;return Rc.current=fs,e===null?fs:e}function kl(){(qc===0||qc===3||qc===2)&&(qc=4),Hc===null||!(Yc&268435455)&&!(Xc&268435455)||xl(Hc,Wc)}function Al(e,t){var n=Vc;Vc|=2;var i=Ol();(Hc!==e||Wc!==t)&&(nl=null,El(e,t));do try{jl();break}catch(t){Dl(e,t)}while(1);if(Ga(),Vc=n,Rc.current=i,Uc!==null)throw Error(r(261));return Hc=null,Wc=0,qc}function jl(){for(;Uc!==null;)Nl(Uc)}function Ml(){for(;Uc!==null&&!ft();)Nl(Uc)}function Nl(e){var t=Wl(e.alternate,e,Gc);e.memoizedProps=e.pendingProps,t===null?Pl(e):Uc=t,zc.current=null}function Pl(e){var t=e;do{var n=t.alternate;if(e=t.return,t.flags&32768){if(n=cc(n,t),n!==null){n.flags&=32767,Uc=n;return}if(e!==null)e.flags|=32768,e.subtreeFlags=0,e.deletions=null;else{qc=6,Uc=null;return}}else if(n=sc(n,t,Gc),n!==null){Uc=n;return}if(t=t.sibling,t!==null){Uc=t;return}Uc=t=e}while(t!==null);qc===0&&(qc=5)}function Fl(e,t,n){var r=zt,i=Bc.transition;try{Bc.transition=null,zt=1,Il(e,t,n,r)}finally{Bc.transition=i,zt=r}return null}function Il(e,t,n,i){do Ll();while(sl!==null);if(Vc&6)throw Error(r(327));n=e.finishedWork;var a=e.finishedLanes;if(n===null)return null;if(e.finishedWork=null,e.finishedLanes=0,n===e.current)throw Error(r(177));e.callbackNode=null,e.callbackPriority=0;var o=n.lanes|n.childLanes;if(Lt(e,o),e===Hc&&(Uc=Hc=null,Wc=0),!(n.subtreeFlags&2064)&&!(n.flags&2064)||ol||(ol=!0,Gl(vt,function(){return Ll(),null})),o=!!(n.flags&15990),n.subtreeFlags&15990||o){o=Bc.transition,Bc.transition=null;var s=zt;zt=1;var c=Vc;Vc|=4,zc.current=null,hc(e,n),Ac(n,e),Mr(yi),fn=!!vi,yi=vi=null,e.current=n,Mc(n,e,a),pt(),Vc=c,zt=s,Bc.transition=o}else e.current=n;if(ol&&(ol=!1,sl=e,cl=a),o=e.pendingLanes,o===0&&(al=null),Ct(n.stateNode,i),gl(e,mt()),t!==null)for(i=e.onRecoverableError,n=0;n<t.length;n++)a=t[n],i(a.value,{componentStack:a.stack,digest:a.digest});if(rl)throw rl=!1,e=il,il=null,e;return cl&1&&e.tag!==0&&Ll(),o=e.pendingLanes,o&1?e===ul?ll++:(ll=0,ul=e):ll=0,sa(),null}function Ll(){if(sl!==null){var e=Bt(cl),t=Bc.transition,n=zt;try{if(Bc.transition=null,zt=16>e?16:e,sl===null)var i=!1;else{if(e=sl,sl=null,cl=0,Vc&6)throw Error(r(331));var a=Vc;for(Vc|=4,Q=e.current;Q!==null;){var o=Q,s=o.child;if(Q.flags&16){var c=o.deletions;if(c!==null){for(var l=0;l<c.length;l++){var u=c[l];for(Q=u;Q!==null;){var d=Q;switch(d.tag){case 0:case 11:case 15:gc(8,d,o)}var f=d.child;if(f!==null)f.return=d,Q=f;else for(;Q!==null;){d=Q;var p=d.sibling,m=d.return;if(yc(d),d===u){Q=null;break}if(p!==null){p.return=m,Q=p;break}Q=m}}}var h=o.alternate;if(h!==null){var g=h.child;if(g!==null){h.child=null;do{var _=g.sibling;g.sibling=null,g=_}while(g!==null)}}Q=o}}if(o.subtreeFlags&2064&&s!==null)s.return=o,Q=s;else b:for(;Q!==null;){if(o=Q,o.flags&2048)switch(o.tag){case 0:case 11:case 15:gc(9,o,o.return)}var v=o.sibling;if(v!==null){v.return=o.return,Q=v;break b}Q=o.return}}var y=e.current;for(Q=y;Q!==null;){s=Q;var b=s.child;if(s.subtreeFlags&2064&&b!==null)b.return=s,Q=b;else b:for(s=y;Q!==null;){if(c=Q,c.flags&2048)try{switch(c.tag){case 0:case 11:case 15:_c(9,c)}}catch(e){zl(c,c.return,e)}if(c===s){Q=null;break b}var x=c.sibling;if(x!==null){x.return=c.return,Q=x;break b}Q=c.return}}if(Vc=a,sa(),St&&typeof St.onPostCommitFiberRoot==`function`)try{St.onPostCommitFiberRoot(xt,e)}catch{}i=!0}return i}finally{zt=n,Bc.transition=t}}return!1}function Rl(e,t,n){t=Ss(n,t),t=Es(e,t,1),e=io(e,t,1),t=pl(),e!==null&&(It(e,1,t),gl(e,t))}function zl(e,t,n){if(e.tag===3)Rl(e,e,n);else for(;t!==null;){if(t.tag===3){Rl(t,e,n);break}if(t.tag===1){var r=t.stateNode;if(typeof t.type.getDerivedStateFromError==`function`||typeof r.componentDidCatch==`function`&&(al===null||!al.has(r))){e=Ss(n,e),e=Ds(t,e,1),t=io(t,e,1),e=pl(),t!==null&&(It(t,1,e),gl(t,e));break}}t=t.return}}function Bl(e,t,n){var r=e.pingCache;r!==null&&r.delete(t),t=pl(),e.pingedLanes|=e.suspendedLanes&n,Hc===e&&(Wc&n)===n&&(qc===4||qc===3&&(Wc&130023424)===Wc&&500>mt()-el?El(e,0):Zc|=n),gl(e,t)}function Vl(e,t){t===0&&(e.mode&1?(t=kt,kt<<=1,!(kt&130023424)&&(kt=4194304)):t=1);var n=pl();e=$a(e,t),e!==null&&(It(e,t,n),gl(e,n))}function Hl(e){var t=e.memoizedState,n=0;t!==null&&(n=t.retryLane),Vl(e,n)}function Ul(e,t){var n=0;switch(e.tag){case 13:var i=e.stateNode,a=e.memoizedState;a!==null&&(n=a.retryLane);break;case 19:i=e.stateNode;break;default:throw Error(r(314))}i!==null&&i.delete(t),Vl(e,n)}var Wl=function(e,t,n){if(e!==null){if(e.memoizedProps!==t.pendingProps||qi.current)Ms=!0;else{if((e.lanes&n)===0&&!(t.flags&128))return Ms=!1,tc(e,t,n);Ms=!!(e.flags&131072)}}else Ms=!1,Ca&&t.flags&1048576&&va(t,da,t.index);switch(t.lanes=0,t.tag){case 2:var i=t.type;$s(e,t),e=t.pendingProps;var a=Yi(t,Ki.current);Ja(t,n),a=K(null,t,i,e,a,n);var o=q();return t.flags|=1,typeof a==`object`&&a&&typeof a.render==`function`&&a.$$typeof===void 0?(t.tag=1,t.memoizedState=null,t.updateQueue=null,Xi(i)?(o=!0,ea(t)):o=!1,t.memoizedState=a.state!==null&&a.state!==void 0?a.state:null,to(t),a.updater=_s,t.stateNode=a,a._reactInternals=t,xs(t,i,e,n),t=Vs(null,t,i,!0,o,n)):(t.tag=0,Ca&&o&&ya(t),Ns(null,t,a,n),t=t.child),t;case 16:i=t.elementType;a:{switch($s(e,t),e=t.pendingProps,a=i._init,i=a(i._payload),t.type=i,a=t.tag=Yl(i),e=hs(i,e),a){case 0:t=zs(null,t,i,e,n);break a;case 1:t=Bs(null,t,i,e,n);break a;case 11:t=Ps(null,t,i,e,n);break a;case 14:t=Fs(null,t,i,hs(i.type,e),n);break a}throw Error(r(306,i,``))}return t;case 0:return i=t.type,a=t.pendingProps,a=t.elementType===i?a:hs(i,a),zs(e,t,i,a,n);case 1:return i=t.type,a=t.pendingProps,a=t.elementType===i?a:hs(i,a),Bs(e,t,i,a,n);case 3:a:{if(Hs(t),e===null)throw Error(r(387));i=t.pendingProps,o=t.memoizedState,a=o.element,no(e,t),so(t,i,null,n);var s=t.memoizedState;if(i=s.element,o.isDehydrated){if(o={element:i,isDehydrated:!1,cache:s.cache,pendingSuspenseBoundaries:s.pendingSuspenseBoundaries,transitions:s.transitions},t.updateQueue.baseState=o,t.memoizedState=o,t.flags&256){a=Ss(Error(r(423)),t),t=Us(e,t,i,n,a);break a}if(i!==a){a=Ss(Error(r(424)),t),t=Us(e,t,i,n,a);break a}for(Sa=Di(t.stateNode.containerInfo.firstChild),xa=t,Ca=!0,wa=null,n=Ba(t,null,i,n),t.child=n;n;)n.flags=n.flags&-3|4096,n=n.sibling}else{if(Ma(),i===a){t=ec(e,t,n);break a}Ns(e,t,i,n)}t=t.child}return t;case 5:return _o(t),e===null&&Oa(t),i=t.type,a=t.pendingProps,o=e===null?null:e.memoizedProps,s=a.children,bi(i,a)?s=null:o!==null&&bi(i,o)&&(t.flags|=32),Rs(e,t),Ns(e,t,s,n),t.child;case 6:return e===null&&Oa(t),null;case 13:return Ks(e,t,n);case 4:return ho(t,t.stateNode.containerInfo),i=t.pendingProps,e===null?t.child=za(t,null,i,n):Ns(e,t,i,n),t.child;case 11:return i=t.type,a=t.pendingProps,a=t.elementType===i?a:hs(i,a),Ps(e,t,i,a,n);case 7:return Ns(e,t,t.pendingProps,n),t.child;case 8:return Ns(e,t,t.pendingProps.children,n),t.child;case 12:return Ns(e,t,t.pendingProps.children,n),t.child;case 10:a:{if(i=t.type._context,a=t.pendingProps,o=t.memoizedProps,s=a.value,Wi(Va,i._currentValue),i._currentValue=s,o!==null){if(Tr(o.value,s)){if(o.children===a.children&&!qi.current){t=ec(e,t,n);break a}}else for(o=t.child,o!==null&&(o.return=t);o!==null;){var c=o.dependencies;if(c!==null){s=o.child;for(var l=c.firstContext;l!==null;){if(l.context===i){if(o.tag===1){l=ro(-1,n&-n),l.tag=2;var u=o.updateQueue;if(u!==null){u=u.shared;var d=u.pending;d===null?l.next=l:(l.next=d.next,d.next=l),u.pending=l}}o.lanes|=n,l=o.alternate,l!==null&&(l.lanes|=n),qa(o.return,n,t),c.lanes|=n;break}l=l.next}}else if(o.tag===10)s=o.type===t.type?null:o.child;else if(o.tag===18){if(s=o.return,s===null)throw Error(r(341));s.lanes|=n,c=s.alternate,c!==null&&(c.lanes|=n),qa(s,n,t),s=o.sibling}else s=o.child;if(s!==null)s.return=o;else for(s=o;s!==null;){if(s===t){s=null;break}if(o=s.sibling,o!==null){o.return=s.return,s=o;break}s=s.return}o=s}}Ns(e,t,a.children,n),t=t.child}return t;case 9:return a=t.type,i=t.pendingProps.children,Ja(t,n),a=Ya(a),i=i(a),t.flags|=1,Ns(e,t,i,n),t.child;case 14:return i=t.type,a=hs(i,t.pendingProps),a=hs(i.type,a),Fs(e,t,i,a,n);case 15:return Is(e,t,t.type,t.pendingProps,n);case 17:return i=t.type,a=t.pendingProps,a=t.elementType===i?a:hs(i,a),$s(e,t),t.tag=1,Xi(i)?(e=!0,ea(t)):e=!1,Ja(t,n),ys(t,i,a),xs(t,i,a,n),Vs(null,t,i,!0,e,n);case 19:return Qs(e,t,n);case 22:return Ls(e,t,n)}throw Error(r(156,t.tag))};function Gl(e,t){return ut(e,t)}function Kl(e,t,n,r){this.tag=e,this.key=n,this.sibling=this.child=this.return=this.stateNode=this.type=this.elementType=null,this.index=0,this.ref=null,this.pendingProps=t,this.dependencies=this.memoizedState=this.updateQueue=this.memoizedProps=null,this.mode=r,this.subtreeFlags=this.flags=0,this.deletions=null,this.childLanes=this.lanes=0,this.alternate=null}function ql(e,t,n,r){return new Kl(e,t,n,r)}function Jl(e){return e=e.prototype,!(!e||!e.isReactComponent)}function Yl(e){if(typeof e==`function`)return+!!Jl(e);if(e!=null){if(e=e.$$typeof,e===j)return 11;if(e===P)return 14}return 2}function Xl(e,t){var n=e.alternate;return n===null?(n=ql(e.tag,t,e.key,e.mode),n.elementType=e.elementType,n.type=e.type,n.stateNode=e.stateNode,n.alternate=e,e.alternate=n):(n.pendingProps=t,n.type=e.type,n.flags=0,n.subtreeFlags=0,n.deletions=null),n.flags=e.flags&14680064,n.childLanes=e.childLanes,n.lanes=e.lanes,n.child=e.child,n.memoizedProps=e.memoizedProps,n.memoizedState=e.memoizedState,n.updateQueue=e.updateQueue,t=e.dependencies,n.dependencies=t===null?null:{lanes:t.lanes,firstContext:t.firstContext},n.sibling=e.sibling,n.index=e.index,n.ref=e.ref,n}function Zl(e,t,n,i,a,o){var s=2;if(i=e,typeof e==`function`)Jl(e)&&(s=1);else if(typeof e==`string`)s=5;else a:switch(e){case E:return Ql(n.children,a,o,t);case D:s=8,a|=8;break;case O:return e=ql(12,n,t,a|2),e.elementType=O,e.lanes=o,e;case M:return e=ql(13,n,t,a),e.elementType=M,e.lanes=o,e;case N:return e=ql(19,n,t,a),e.elementType=N,e.lanes=o,e;case ee:return $l(n,a,o,t);default:if(typeof e==`object`&&e)switch(e.$$typeof){case k:s=10;break a;case A:s=9;break a;case j:s=11;break a;case P:s=14;break a;case F:s=16,i=null;break a}throw Error(r(130,e==null?e:typeof e,``))}return t=ql(s,n,t,a),t.elementType=e,t.type=i,t.lanes=o,t}function Ql(e,t,n,r){return e=ql(7,e,r,t),e.lanes=n,e}function $l(e,t,n,r){return e=ql(22,e,r,t),e.elementType=ee,e.lanes=n,e.stateNode={isHidden:!1},e}function eu(e,t,n){return e=ql(6,e,null,t),e.lanes=n,e}function tu(e,t,n){return t=ql(4,e.children===null?[]:e.children,e.key,t),t.lanes=n,t.stateNode={containerInfo:e.containerInfo,pendingChildren:null,implementation:e.implementation},t}function nu(e,t,n,r,i){this.tag=t,this.containerInfo=e,this.finishedWork=this.pingCache=this.current=this.pendingChildren=null,this.timeoutHandle=-1,this.callbackNode=this.pendingContext=this.context=null,this.callbackPriority=0,this.eventTimes=Ft(0),this.expirationTimes=Ft(-1),this.entangledLanes=this.finishedLanes=this.mutableReadLanes=this.expiredLanes=this.pingedLanes=this.suspendedLanes=this.pendingLanes=0,this.entanglements=Ft(0),this.identifierPrefix=r,this.onRecoverableError=i,this.mutableSourceEagerHydrationData=null}function ru(e,t,n,r,i,a,o,s,c){return e=new nu(e,t,n,s,c),t===1?(t=1,!0===a&&(t|=8)):t=0,a=ql(3,null,null,t),e.current=a,a.stateNode=e,a.memoizedState={element:r,isDehydrated:n,cache:null,transitions:null,pendingSuspenseBoundaries:null},to(a),e}function iu(e,t,n){var r=3<arguments.length&&arguments[3]!==void 0?arguments[3]:null;return{$$typeof:T,key:r==null?null:``+r,children:e,containerInfo:t,implementation:n}}function au(e){if(!e)return Gi;e=e._reactInternals;a:{if(it(e)!==e||e.tag!==1)throw Error(r(170));var t=e;do{switch(t.tag){case 3:t=t.stateNode.context;break a;case 1:if(Xi(t.type)){t=t.stateNode.__reactInternalMemoizedMergedChildContext;break a}}t=t.return}while(t!==null);throw Error(r(171))}if(e.tag===1){var n=e.type;if(Xi(n))return $i(e,n,t)}return t}function ou(e,t,n,r,i,a,o,s,c){return e=ru(n,r,!0,e,i,a,o,s,c),e.context=au(null),n=e.current,r=pl(),i=ml(n),a=ro(r,i),a.callback=t??null,io(n,a,i),e.current.lanes=i,It(e,i,r),gl(e,r),e}function su(e,t,n,r){var i=t.current,a=pl(),o=ml(i);return n=au(n),t.context===null?t.context=n:t.pendingContext=n,t=ro(a,o),t.payload={element:e},r=r===void 0?null:r,r!==null&&(t.callback=r),e=io(i,t,o),e!==null&&(hl(e,i,o,a),ao(e,i,o)),o}function cu(e){if(e=e.current,!e.child)return null;switch(e.child.tag){case 5:return e.child.stateNode;default:return e.child.stateNode}}function lu(e,t){if(e=e.memoizedState,e!==null&&e.dehydrated!==null){var n=e.retryLane;e.retryLane=n!==0&&n<t?n:t}}function uu(e,t){lu(e,t),(e=e.alternate)&&lu(e,t)}function du(){return null}var fu=typeof reportError==`function`?reportError:function(e){console.error(e)};function pu(e){this._internalRoot=e}mu.prototype.render=pu.prototype.render=function(e){var t=this._internalRoot;if(t===null)throw Error(r(409));su(e,t,null,null)},mu.prototype.unmount=pu.prototype.unmount=function(){var e=this._internalRoot;if(e!==null){this._internalRoot=null;var t=e.containerInfo;wl(function(){su(null,e,null,null)}),t[Mi]=null}};function mu(e){this._internalRoot=e}mu.prototype.unstable_scheduleHydration=function(e){if(e){var t=Wt();e={blockedOn:null,target:e,priority:t};for(var n=0;n<$t.length&&t!==0&&t<$t[n].priority;n++);$t.splice(n,0,e),n===0&&an(e)}};function hu(e){return!(!e||e.nodeType!==1&&e.nodeType!==9&&e.nodeType!==11)}function gu(e){return!(!e||e.nodeType!==1&&e.nodeType!==9&&e.nodeType!==11&&(e.nodeType!==8||e.nodeValue!==` react-mount-point-unstable `))}function _u(){}function vu(e,t,n,r,i){if(i){if(typeof r==`function`){var a=r;r=function(){var e=cu(o);a.call(e)}}var o=ou(t,r,e,0,null,!1,!1,``,_u);return e._reactRootContainer=o,e[Mi]=o.current,oi(e.nodeType===8?e.parentNode:e),wl(),o}for(;i=e.lastChild;)e.removeChild(i);if(typeof r==`function`){var s=r;r=function(){var e=cu(c);s.call(e)}}var c=ru(e,0,!1,null,null,!1,!1,``,_u);return e._reactRootContainer=c,e[Mi]=c.current,oi(e.nodeType===8?e.parentNode:e),wl(function(){su(t,c,n,r)}),c}function yu(e,t,n,r,i){var a=n._reactRootContainer;if(a){var o=a;if(typeof i==`function`){var s=i;i=function(){var e=cu(o);s.call(e)}}su(t,o,e,i)}else o=vu(n,t,e,i,r);return cu(o)}Vt=function(e){switch(e.tag){case 3:var t=e.stateNode;if(t.current.memoizedState.isDehydrated){var n=At(t.pendingLanes);n!==0&&(Rt(t,n|1),gl(t,mt()),!(Vc&6)&&(tl=mt()+500,sa()))}break;case 13:wl(function(){var t=$a(e,1);t!==null&&hl(t,e,1,pl())}),uu(e,1)}},Ht=function(e){if(e.tag===13){var t=$a(e,134217728);t!==null&&hl(t,e,134217728,pl()),uu(e,134217728)}},Ut=function(e){if(e.tag===13){var t=ml(e),n=$a(e,t);n!==null&&hl(n,e,t,pl()),uu(e,t)}},Wt=function(){return zt},Gt=function(e,t){var n=zt;try{return zt=e,t()}finally{zt=n}},Le=function(e,t,n){switch(t){case`input`:if(ve(e,n),t=n.name,n.type===`radio`&&t!=null){for(n=e;n.parentNode;)n=n.parentNode;for(n=n.querySelectorAll(`input[name=`+JSON.stringify(``+t)+`][type="radio"]`),t=0;t<n.length;t++){var i=n[t];if(i!==e&&i.form===e.form){var a=zi(i);if(!a)throw Error(r(90));pe(i),ve(i,a)}}}break;case`textarea`:Ce(e,n);break;case`select`:t=n.value,t!=null&&xe(e,!!n.multiple,t,!1)}},Ue=Cl,We=wl;var bu={usingClientEntryPoint:!1,Events:[Li,Ri,zi,Ve,He,Cl]},xu={findFiberByHostInstance:Ii,bundleType:0,version:`18.3.1`,rendererPackageName:`react-dom`},Su={bundleType:xu.bundleType,version:xu.version,rendererPackageName:xu.rendererPackageName,rendererConfig:xu.rendererConfig,overrideHookState:null,overrideHookStateDeletePath:null,overrideHookStateRenamePath:null,overrideProps:null,overridePropsDeletePath:null,overridePropsRenamePath:null,setErrorHandler:null,setSuspenseHandler:null,scheduleUpdate:null,currentDispatcherRef:C.ReactCurrentDispatcher,findHostInstanceByFiber:function(e){return e=ct(e),e===null?null:e.stateNode},findFiberByHostInstance:xu.findFiberByHostInstance||du,findHostInstancesForRefresh:null,scheduleRefresh:null,scheduleRoot:null,setRefreshHandler:null,getCurrentFiber:null,reconcilerVersion:`18.3.1-next-f1338f8080-20240426`};if(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__<`u`){var Cu=__REACT_DEVTOOLS_GLOBAL_HOOK__;if(!Cu.isDisabled&&Cu.supportsFiber)try{xt=Cu.inject(Su),St=Cu}catch{}}e.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED=bu,e.createPortal=function(e,t){var n=2<arguments.length&&arguments[2]!==void 0?arguments[2]:null;if(!hu(t))throw Error(r(200));return iu(e,t,null,n)},e.createRoot=function(e,t){if(!hu(e))throw Error(r(299));var n=!1,i=``,a=fu;return t!=null&&(!0===t.unstable_strictMode&&(n=!0),t.identifierPrefix!==void 0&&(i=t.identifierPrefix),t.onRecoverableError!==void 0&&(a=t.onRecoverableError)),t=ru(e,1,!1,null,null,n,!1,i,a),e[Mi]=t.current,oi(e.nodeType===8?e.parentNode:e),new pu(t)},e.findDOMNode=function(e){if(e==null)return null;if(e.nodeType===1)return e;var t=e._reactInternals;if(t===void 0)throw typeof e.render==`function`?Error(r(188)):(e=Object.keys(e).join(`,`),Error(r(268,e)));return e=ct(t),e=e===null?null:e.stateNode,e},e.flushSync=function(e){return wl(e)},e.hydrate=function(e,t,n){if(!gu(t))throw Error(r(200));return yu(null,e,t,!0,n)},e.hydrateRoot=function(e,t,n){if(!hu(e))throw Error(r(405));var i=n!=null&&n.hydratedSources||null,a=!1,o=``,s=fu;if(n!=null&&(!0===n.unstable_strictMode&&(a=!0),n.identifierPrefix!==void 0&&(o=n.identifierPrefix),n.onRecoverableError!==void 0&&(s=n.onRecoverableError)),t=ou(t,null,e,1,n??null,a,!1,o,s),e[Mi]=t.current,oi(e),i)for(e=0;e<i.length;e++)n=i[e],a=n._getVersion,a=a(n._source),t.mutableSourceEagerHydrationData==null?t.mutableSourceEagerHydrationData=[n,a]:t.mutableSourceEagerHydrationData.push(n,a);return new mu(t)},e.render=function(e,t,n){if(!gu(t))throw Error(r(200));return yu(null,e,t,!1,n)},e.unmountComponentAtNode=function(e){if(!gu(e))throw Error(r(40));return e._reactRootContainer?(wl(function(){yu(null,null,e,!1,function(){e._reactRootContainer=null,e[Mi]=null})}),!0):!1},e.unstable_batchedUpdates=Cl,e.unstable_renderSubtreeIntoContainer=function(e,t,n,i){if(!gu(n))throw Error(r(200));if(e==null||e._reactInternals===void 0)throw Error(r(38));return yu(e,t,n,!1,i)},e.version=`18.3.1-next-f1338f8080-20240426`})),m=o(((e,t)=>{function n(){if(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__<`u`&&typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE==`function`)try{__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(n)}catch(e){console.error(e)}}n(),t.exports=p()})),h=o((e=>{var t=m();e.createRoot=t.createRoot,e.hydrateRoot=t.hydrateRoot})),g=c(u(),1),_=h(),v=[`#1f77b4`,`#aec7e8`,`#ff7f0e`,`#ffbb78`,`#2ca02c`,`#98df8a`,`#d62728`,`#ff9896`,`#9467bd`,`#c5b0d5`,`#8c564b`,`#c49c94`,`#e377c2`,`#f7b6d2`,`#7f7f7f`,`#c7c7c7`,`#bcbd22`,`#dbdb8d`,`#17becf`,`#9edae5`],y=[`#e6194b`,`#3cb44b`,`#ffe119`,`#4363d8`,`#f58231`,`#911eb4`,`#46f0f0`,`#f032e6`,`#bcf60c`,`#fabebe`,`#008080`,`#e6beff`,`#9a6324`,`#fffac8`,`#800000`,`#aaffc3`,`#808000`,`#ffd8b1`,`#6b8cff`,`#ff6f91`,`#00c2a8`,`#c9a0ff`,`#ffa600`,`#7fdbff`];function b(e){let t=e.trim().replace(/^#/,``);if(t.length===3&&(t=t.split(``).map(e=>e+e).join(``)),!/^[0-9a-fA-F]{6}$/.test(t))throw Error(`bad colour "${e}"`);let n=parseInt(t,16);return[(n>>16&255)/255,(n>>8&255)/255,(n&255)/255]}function x(e){let t=e.replace(/^chr/i,``);if(/^\d+$/.test(t))return parseInt(t,10)-1;let n={x:22,y:23,m:24,mt:24},r=t.toLowerCase();if(r in n)return n[r];let i=2166136261;for(let t=0;t<e.length;t++)i^=e.charCodeAt(t),i=Math.imul(i,16777619);return(i>>>0)+1e3}function S(e){return y[x(e)%y.length]}function C(e){return I(e*.618033988749895%1,.8,1)}var w=[[.267,.005,.329],[.279,.175,.483],[.23,.322,.546],[.173,.449,.558],[.128,.567,.551],[.153,.681,.504],[.361,.786,.388],[.668,.862,.196],[.993,.906,.144]];function T(e){let t=Math.min(1,Math.max(0,Number.isFinite(e)?e:0))*(w.length-1),n=Math.min(w.length-2,Math.floor(t)),r=t-n,i=w[n],a=w[n+1];return[i[0]+(a[0]-i[0])*r,i[1]+(a[1]-i[1])*r,i[2]+(a[2]-i[2])*r]}var E=[.45,.45,.45];function D(e){let t=[];for(let n of e)typeof n==`number`&&Number.isFinite(n)&&t.push(n);if(!t.length)return[0,1];t.sort((e,t)=>e-t);let n=t[0],r=t[Math.min(t.length-1,Math.floor(.99*(t.length-1)+1e-9))];return r>n?[n,r]:[n,n+1]}function O(e,t){return typeof e!=`number`||!Number.isFinite(e)?E:T((e-t[0])/(t[1]-t[0]))}var k=[.24,.24,.26];function A(e,t){return e<24?N(e):F(t)}function j(e,t=[],n){let r=new Set(t),i=(e.categories??[]).map(e=>e.value);if(n){let e=new Set(i);for(let t of n)typeof t==`string`&&!e.has(t)&&(e.add(t),i.push(t))}return new Map(i.map((e,t)=>[e,r.has(e)?-1:t]))}function M(e,t){if(t.categories){if(e==null)return E;let n=t.categories.get(String(e));return n===void 0?E:n<0?k:A(n,String(e))}return O(e,t.fieldRange??D(t.cellValues?.values()??[]))}function N(e){let t=(e%24+24)%24,n=t%12*7%12;return t<12?I(n/12,.78,1):I(n/12,.4,1)}function P(e){let t=new Map(e.map((e,t)=>[e,t]));return e=>{let n=t.get(e);return n!==void 0&&n<24?N(n):F(e)}}function F(e){let t=2166136261;for(let n=0;n<e.length;n++)t^=e.charCodeAt(n),t=Math.imul(t,16777619);return I((t>>>0)%997*.618033988749895%1,.7,1)}function ee(e){for(let t=0;t<e.length;t++){let n=e[t];e[t]=n<=.04045?n/12.92:((n+.055)/1.055)**2.4}return e}var te=e=>`rgb(${Math.round(e[0]*255)}, ${Math.round(e[1]*255)}, ${Math.round(e[2]*255)})`;function I(e,t,n){let r=Math.floor(e*6),i=e*6-r,a=n*(1-t),o=n*(1-i*t),s=n*(1-(1-i)*t);switch((r%6+6)%6){case 0:return[n,s,a];case 1:return[o,n,a];case 2:return[a,n,s];case 3:return[a,o,n];case 4:return[s,a,n];default:return[n,a,o]}}function L(e){return I((1-Math.min(1,Math.max(0,e)))*.75,.85,1)}var ne=[.72,.74,.78];function re(e,t,n,r={}){if(t===`cell`){let t=r.cellIndex?.get(e);return t===void 0?[.6,.6,.6]:C(t)}return t===`field`?M(r.cellValues?.get(e),r):t===`custom`?b(n):ne}function ie(e,t,n,r={}){let i=r.chromColors??!1,{header:a,starts:o,offsets:s}=e,c=a.n_points,l=new Float32Array(3*c),u=(e,t,n)=>{for(let r=e;r<t;r++)l[3*r]=n[0],l[3*r+1]=n[1],l[3*r+2]=n[2]};if(t===`custom`)return u(0,c,b(n)),l;if(t===`field`){let e=r.cellValues??new Map,t={...r,fieldRange:r.fieldRange??D(e.values())},n=new Map;return a.segments.forEach((r,i)=>{if(r.cell_id===null)return u(s[i],s[i+1],E);let a=n.get(r.cell_id);a||n.set(r.cell_id,a=M(e.get(r.cell_id),t)),u(s[i],s[i+1],a)}),l}if(t===`cell`){let e=new Map(r.cellIndex??[]),t=[.6,.6,.6];return a.segments.forEach((n,r)=>{if(n.cell_id===null)return u(s[r],s[r+1],t);e.has(n.cell_id)||e.set(n.cell_id,e.size),u(s[r],s[r+1],C(e.get(n.cell_id)))}),l}if(t===`trace`){let e=new Map;return a.segments.forEach((t,n)=>{e.has(t.trace_id)||e.set(t.trace_id,e.size),u(s[n],s[n+1],b(v[e.get(t.trace_id)%v.length]))}),l}return new Set(a.segments.map(e=>e.chrom)).size>1||i?(a.segments.forEach((e,t)=>u(s[t],s[t+1],b(S(e.chrom)))),l):(a.segments.forEach((e,t)=>{let n=a.chrom_extent[e.chrom]??[e.start,e.end],r=Math.max(1,n[1]-n[0]);for(let e=s[t];e<s[t+1];e++){let t=L((o[e]-n[0])/r);l[3*e]=t[0],l[3*e+1]=t[1],l[3*e+2]=t[2]}}),l)}function ae(e){if(e.byteLength<4)throw Error(`matrix payload too short`);let t=new DataView(e).getUint32(0,!0);if(t%4!=0)throw Error(`header length ${t} is not a multiple of 4`);if(4+t>e.byteLength)throw Error(`matrix header overruns the payload`);let n=JSON.parse(new TextDecoder().decode(new Uint8Array(e,4,t))),r=n.n_rows*n.n_cols,i=4+t+4*r;if(e.byteLength!==i)throw Error(`matrix payload is ${e.byteLength} bytes, expected ${i}`);return{header:n,data:new Float32Array(e,4+t,r)}}function oe(e){return e===`distance`?`distance`:e===`contact_frequency`?`frequency`:`contacts`}function se(e,t,n){let r=[];for(let t=0;t<e.length;t++){let i=n?n(e[t]):e[t];Number.isFinite(i)&&r.push(i)}return r.length?(r.sort((e,t)=>e-t),r[Math.min(r.length-1,Math.max(0,Math.round(t*(r.length-1))))]):NaN}function ce(e,t){if(t===`contacts`){let t=se(e,.99,e=>e>0?Math.log1p(e):NaN);return[0,Number.isFinite(t)&&t>0?t:1]}if(t===`frequency`){let t=se(e,1);return[0,Number.isFinite(t)&&t>0?t:1]}let n=se(e,.01),r=se(e,.99);return Number.isFinite(n)?r>n?[n,r]:[n,n+1]:[0,1]}var le=[[1,1,1],[1,.96,.62],[1,.72,.3],[.94,.33,.13],[.7,.05,.08],[.3,0,.03]];function ue(e){let t=Math.min(1,Math.max(0,Number.isFinite(e)?e:0))*(le.length-1),n=Math.min(le.length-2,Math.floor(t)),r=t-n,i=le[n],a=le[n+1];return[i[0]+(a[0]-i[0])*r,i[1]+(a[1]-i[1])*r,i[2]+(a[2]-i[2])*r]}var de=[.38,.38,.4];function fe(e,t,n){if(!Number.isFinite(e))return de;let[r,i]=n;if(t===`contacts`)return ue((e>0?Math.log1p(e):0)/(i||1));let a=(e-r)/(i-r||1);return T(t===`distance`?1-a:a)}function pe(e,t,n){let{n_rows:r,n_cols:i}=e.header,a=new Uint8ClampedArray(4*r*i);for(let o=0;o<r*i;o++){let r=fe(e.data[o],t,n);a[4*o]=r[0]*255,a[4*o+1]=r[1]*255,a[4*o+2]=r[2]*255,a[4*o+3]=255}return a}function me(e,t,n){let r=0,i=e.length-1;if(i<0||n<e[0]||n>=t[i])return-1;for(;r<i;){let t=r+i+1>>1;e[t]<=n?r=t:i=t-1}return n<t[r]?r:-1}async function he(e,t){let n=await fetch(e,t);if(!n.ok){let e=`${n.status} ${n.statusText}`;try{let t=await n.json();t&&t.detail&&(e=typeof t.detail==`string`?t.detail:JSON.stringify(t.detail))}catch{}throw Error(e)}return n}async function ge(){return(await he(`api/health`)).json()}async function _e(){return(await he(`api/datasets`)).json()}async function ve(e){return(await he(`api/datasets`,{method:`POST`,headers:{"Content-Type":`application/json`},body:JSON.stringify({path:e})})).json()}async function ye(e){await he(`api/datasets/${encodeURIComponent(e)}`,{method:`DELETE`})}async function R(e,t={}){let n=new URLSearchParams;return t.chrom&&n.set(`chrom`,t.chrom),n.set(`offset`,String(t.offset??0)),n.set(`limit`,String(t.limit??500)),(await he(`api/datasets/${encodeURIComponent(e)}/traces?${n}`)).json()}async function be(e,t={}){let n=new URLSearchParams({offset:String(t.offset??0),limit:String(t.limit??500)});return(await he(`api/datasets/${encodeURIComponent(e)}/cells?${n}`)).json()}async function xe(e,t){let n=new URLSearchParams({field:t});return(await he(`api/datasets/${encodeURIComponent(e)}/cell_values?${n}`)).json()}async function Se(e,t){let n=new URLSearchParams({cell_id:t});return(await he(`api/datasets/${encodeURIComponent(e)}/cell_info?${n}`)).json()}async function z(e,t,n){let r=new URLSearchParams({dims:`${n[0]},${n[1]}`});return(await he(`api/datasets/${encodeURIComponent(e)}/embedding/${encodeURIComponent(t)}?${r}`)).json()}async function Ce(e,t){return B(t,await(await he(`api/datasets/${encodeURIComponent(e)}/points/${encodeURIComponent(t)}`,{method:`POST`,headers:{"Content-Type":`application/json`},body:`{}`})).json())}function B(e,t){if(t.positions.length!==3*t.n||t.cell_ids.length!==t.n||t.labels.length!==t.n)throw Error(`point set ${e}: inconsistent lengths`);return{name:e,n:t.n,positions:Float32Array.from(t.positions,e=>e===null?NaN:e),cellIds:t.cell_ids.map(e=>e===null?null:String(e)),labels:t.labels.map(e=>e===null?``:String(e)),values:t.values??{}}}async function V(e,t,n){let r={...t};return n!==void 0&&(r.max_points=n),we(await(await he(`api/datasets/${encodeURIComponent(e)}/geometry`,{method:`POST`,headers:{"Content-Type":`application/json`},body:JSON.stringify(r)})).arrayBuffer())}function we(e){if(e.byteLength<4)throw Error(`geometry payload too short`);let t=new DataView(e).getUint32(0,!0);if(t%4!=0)throw Error(`header length ${t} is not a multiple of 4`);let n=new Uint8Array(e,4,t),r=JSON.parse(new TextDecoder().decode(n)),i=r.n_points,a=r.n_segments,o=4+t,s=o+12*i+4*i+4*(a+1);if(e.byteLength!==s)throw Error(`geometry payload is ${e.byteLength} bytes, expected ${s}`);let c=new Float32Array(e,o,3*i);o+=12*i;let l=new Uint32Array(e,o,i);return o+=4*i,{header:r,positions:c,starts:l,offsets:new Uint32Array(e,o,a+1)}}var Te=e=>`api/datasets/${encodeURIComponent(e)}`;async function Ee(e,t,n){return(await he(`${Te(e)}/groups`,{method:`POST`,headers:{"Content-Type":`application/json`},body:JSON.stringify({cells:t,name:n??null})})).json()}var De=()=>null;function Oe(e){De=e}var ke=new Map;async function Ae(e,t){if(!t)return null;if(t.startsWith(`field:`))return t;let n=`${e}\u0000${t}`,r=ke.get(n);if(!r){let i=De(e,t);if(!i)return t;r=Ee(e,i).then(e=>e.id),r.catch(()=>ke.delete(n)),ke.set(n,r)}return r}function je(e){let t=new URLSearchParams;for(let[n,r]of Object.entries(e))r!=null&&r!==``&&t.set(n,String(r));let n=t.toString();return n?`?${n}`:``}async function Me(e,t,n,r={}){let i=await Ae(e,r.group),a=je({names:t.join(`,`),chrom:n.chrom,start:n.start,end:n.end,cell_id:r.cellId,agg:r.agg,group:i});return(await he(`${Te(e)}/tracks${a}`)).json()}async function Ne(e,t,n){return(await he(`${Te(e)}/intervals/${encodeURIComponent(t)}${je({chrom:n.chrom,start:n.start,end:n.end})}`)).json()}async function Pe(e,t,n,r={}){let i=await Ae(e,r.group),a=je({chrom:n.chrom,start:n.start,end:n.end,resolution:r.resolution,balance:r.balance?`true`:`false`,cell:r.cell,group:i});return ae(await(await he(`${Te(e)}/contacts/${encodeURIComponent(t)}${a}`)).arrayBuffer())}async function Fe(e,t,n={}){let r=await Ae(e,n.group),i=je({chrom:t.chrom,start:t.start,end:t.end,cell_id:n.cellId,trace_id:n.traceId,stat:n.stat,threshold:n.threshold,group:r});return ae(await(await he(`${Te(e)}/distance${i}`)).arrayBuffer())}async function Ie(e,t={}){let n=await Ae(e,t.group);return(await he(`${Te(e)}/stats/rg${je({chrom:t.chrom,cell_id:t.cellId,group:n})}`)).json()}async function Le(e,t={}){let n=await Ae(e,t.group);return(await he(`${Te(e)}/stats/scaling${je({chrom:t.chrom,cell_id:t.cellId,group:n})}`)).json()}var Re=e=>{let t,n=new Set,r=(e,r)=>{let i=typeof e==`function`?e(t):e;if(!Object.is(i,t)){let e=t;t=r??(typeof i!=`object`||!i)?i:Object.assign({},t,i),n.forEach(n=>n(t,e))}},i=()=>t,a={setState:r,getState:i,getInitialState:()=>o,subscribe:e=>(n.add(e),()=>n.delete(e))},o=t=e(r,i,a);return a},ze=(e=>e?Re(e):Re),Be=e=>e;function Ve(e,t=Be){let n=g.useSyncExternalStore(e.subscribe,g.useCallback(()=>t(e.getState()),[e,t]),g.useCallback(()=>t(e.getInitialState()),[e,t]));return g.useDebugValue(n),n}var He=e=>{let t=ze(e),n=e=>Ve(t,e);return Object.assign(n,t),n},Ue=(e=>e?He(e):He),We=`field:`,Ge=(e,t)=>`${We}${e}=${t}`;function Ke(e){if(!e.startsWith(`field:`))return null;let t=e.slice(6),n=t.indexOf(`=`);return n<=0?null:{field:t.slice(0,n),value:t.slice(n+1)}}function qe(e,t){if(!e)return null;let n=[];for(let[r,i]of e)i!==null&&String(i)===t&&n.push(r);return n}function Je(e,t,n){let r=!1;for(let i=0,a=n.length-1;i<n.length;a=i++){let[o,s]=n[i],[c,l]=n[a];s>t!=l>t&&e<(c-o)*(t-s)/(l-s)+o&&(r=!r)}return r}function Ye(e,t,n){if(n.length<3)return[];let[r,i,a,o]=[1/0,1/0,-1/0,-1/0];for(let[e,t]of n)r=Math.min(r,e),i=Math.min(i,t),a=Math.max(a,e),o=Math.max(o,t);let s=[];for(let c=0;c<t.length;c++){let l=e[2*c],u=e[2*c+1];l>=r&&l<=a&&u>=i&&u<=o&&Je(l,u,n)&&s.push(t[c])}return s}function Xe(e,t=2){let n=[];for(let r of e){let e=n[n.length-1];(!e||Math.hypot(r[0]-e[0],r[1]-e[1])>=t)&&n.push(r)}return n}function Ze(e){return te(N(e+3))}function Qe(e,t=`selection`){let n=new Set(e.map(e=>e.name)),r=1;for(;n.has(`${t} ${r}`);)r++;return`${t} ${r}`}function $e(e,t){return e.some(e=>e.id===t.id)?e.map(e=>e.id===t.id?{...e,...t}:e):[...e,t]}function et(e,t,n){let r=n.trim();return r?e.map(e=>e.id===t?{...e,name:r}:e):[...e]}function tt(e,t){return e.filter(e=>e.id!==t)}function nt(e){let t={};if(!e||typeof e!=`object`||Array.isArray(e))return t;for(let[n,r]of Object.entries(e)){if(!Array.isArray(r))continue;let e=r.filter(e=>!!e&&typeof e.id==`string`&&typeof e.name==`string`&&typeof e.color==`string`&&Array.isArray(e.cells)&&e.cells.every(e=>typeof e==`string`));e.length&&(t[n]=e.map(e=>({id:e.id,name:e.name,color:e.color,cells:[...e.cells]})))}return t}var rt={kind:`all`},it={kind:`focus`};function at(e,t){let n=e??it;return n.kind===`all`?rt:n.kind===`cell`?{kind:`cell`,cell:n.cell}:n.kind===`group`?{kind:`group`,group:n.group}:t.focusCell?{kind:`cell`,cell:t.focusCell}:t.focusGroup?{kind:`group`,group:t.focusGroup}:rt}function ot(e,t,n){return!e||e.kind===`view`?t:at(e,n)}function st(e,t=!1){if(!e||typeof e!=`object`)return null;let n=e;return n.kind===`all`||n.kind===`focus`?{kind:n.kind}:n.kind===`view`?t?{kind:`view`}:null:n.kind===`cell`&&typeof n.cell==`string`&&n.cell?{kind:`cell`,cell:n.cell}:n.kind===`group`&&typeof n.group==`string`&&n.group?{kind:`group`,group:n.group}:null}var ct=(e,t)=>JSON.stringify(e??null)===JSON.stringify(t??null),lt=e=>e.kind!==`cell`;function ut(e){return{cellId:e.kind===`cell`?e.cell:null,group:e.kind===`group`?e.group:null}}var dt=e=>e.kind===`all`?`all`:e.kind===`cell`?`cell:${e.cell}`:`group:${e.group}`;function ft(e,t){let n=Ke(e);if(n){let r=t.fields.find(e=>e.name===n.field);if(!r)return null;let i=(r.categories??[]).findIndex(e=>e.value===n.value);return{ref:e,name:n.value,color:te(A(Math.max(0,i),n.value)),cells:qe(t.values(n.field),n.value),kind:`field`}}let r=t.saved.find(t=>t.id===e);return r?{ref:e,name:r.name,color:r.color,cells:r.cells,kind:`saved`}:t.selection?.id===e?{ref:e,name:`selection`,color:`#ffffff`,cells:t.selection.cells,kind:`selection`}:null}function pt(e,t,n){if(e.kind===`all`)return n?`All cells (${n})`:`All cells`;if(e.kind===`cell`)return`cell ${e.cell}`;let r=t?.cells?.length;return`${t?.name??e.group}${r===void 0?``:` (${r} cells)`}`}function mt(e,t,n){if(e.kind===`all`)return n?`All cells · ${n}`:`All cells`;if(e.kind===`cell`)return`cell ${e.cell}`;let r=t?.cells?.length;return`${t?.name??e.group}${r===void 0?``:` · ${r} cells`}`}function ht(e,t,n,r,i){let a=e??it,o=pt(t,n,r),s=e=>{let t=i?.get(e);return typeof t==`string`?` · ${t}`:``};return a.kind===`view`?`Same as view → ${t.kind===`cell`?o+s(t.cell):o}`:a.kind===`focus`?`Follow focus → ${t.kind===`cell`?o+s(t.cell):o}`:a.kind===`all`?o:a.kind===`cell`?`📌 ${o}${s(a.cell)}`:`Group: ${o}`}var gt={mode:`line`,colorMode:`rainbow`,color:`#4fc3f7`,opacity:1,lineWidth:1,tubeRadius:null,pointSize:4,highQuality:!1};function _t(e,t){let n=new Set([t]),r=!0;for(;r;){r=!1;for(let t of e)t.parentId&&n.has(t.parentId)&&!n.has(t.id)&&(n.add(t.id),r=!0)}return n}function vt(e,t){let n=_t(e,t);return e.filter(e=>!n.has(e.id))}function yt(e){let t=new Map,n=new Set(e.map(e=>e.id));for(let r of e){let e=r.parentId&&n.has(r.parentId)?r.parentId:null;t.has(e)||t.set(e,[]),t.get(e).push(r)}let r=[],i=(e,n)=>{for(let a of t.get(e)??[])r.push({layer:a,depth:n}),i(a.id,n+1)};return i(null,0),r}function bt(e,t){let n=new Set(e.map(e=>e.name));if(!n.has(t))return t;for(let e=2;;e++){let r=`${t} (${e})`;if(!n.has(r))return r}}var xt=e=>!!e&&e.kind===`point`,St={"":1,b:1,bp:1,k:1e3,kb:1e3,m:1e6,mb:1e6,g:1e9,gb:1e9};function Ct(e){let t=e.trim().toLowerCase().replace(/[,_\s]/g,``),n=/^(\d+(?:\.\d+)?)([a-z]*)$/.exec(t);if(!n||!(n[2]in St))throw Error(`not a genomic position: "${e}"`);return Math.round(parseFloat(n[1])*St[n[2]])}function wt(e){let t=e.trim().split(/\s*(?:-|–|\.\.|:)\s*/);if(t.length!==2||!t[0]||!t[1])throw Error(`expected "start-end", got "${e}"`);let n=Ct(t[0]),r=Ct(t[1]);if(r<=n)throw Error(`end must be greater than start`);return{start:n,end:r}}function Tt(e,t){let{start:n,end:r}=wt(t);if(r<=e.start||n>=e.end)throw Error(`${e.name}:${H(n)}-${H(r)} is outside ${H(e.start)}-${H(e.end)}`);return{chrom:e.name,start:n,end:r}}function Et(e,t){return Dt(e,t,`trace`)}function Dt(e,t,n){let r=new Set(t),i=[],a=new Set,o=e=>{a.has(e)||(a.add(e),i.push(e))},s=e.split(`,`).map(e=>e.trim()).filter(Boolean);if(s.length===0)throw Error(`empty ${n} selection`);for(let e of s){if(r.has(e)){o(e);continue}let i=/^(\d+)\s*-\s*(\d+)$/.exec(e);if(i){let n=parseInt(i[1],10),r=parseInt(i[2],10);if(n<1||r<n||r>t.length)throw Error(`range ${e} is outside 1-${t.length}`);for(let e=n;e<=r;e++)o(t[e-1]);continue}throw Error(`unknown ${n} "${e}"`)}return i}function Ot(e,t){if(!e)return t?[...t]:void 0;if(!t)return[...e];let n=new Set(t);return e.filter(e=>n.has(e))}function kt(e,t){let n={},r=Ot(e.chroms,t.chroms);if(r){if(r.length===0)return null;n.chroms=r}let i=e.region;if(t.region){if(i){if(i.chrom!==t.region.chrom)return null;let e=Math.max(i.start,t.region.start),n=Math.min(i.end,t.region.end);if(n<=e)return null;i={chrom:i.chrom,start:e,end:n}}else i={...t.region}}if(i){if(n.chroms&&!n.chroms.includes(i.chrom))return null;n.region=i}let a=Ot(e.trace_ids,t.trace_ids);if(a){if(a.length===0)return null;n.trace_ids=a}let o=Ot(e.cell_ids,t.cell_ids);if(o){if(o.length===0)return null;n.cell_ids=o}return n}function At(e,t){if(e.region)return t.filter(t=>t.name===e.region.chrom);if(e.chroms){let n=new Set(e.chroms);return t.filter(e=>n.has(e.name))}return t}function H(e){return e>=1e6&&e%1e3==0?`${+(e/1e6).toFixed(3)}M`:e>=1e3&&e%1==0&&e%10==0?`${+(e/1e3).toFixed(2)}k`:e.toLocaleString(`en-US`)}function jt(e){if(e.region)return`${e.region.chrom}:${H(e.region.start)}-${H(e.region.end)}`;if(e.cell_ids){let t=e.cell_ids;return t.length<=3?`cell ${t.join(`, `)}`:`${t.length} cells`}if(e.trace_ids){let t=e.trace_ids;return t.length<=3?`trace ${t.join(`, `)}`:`${t.length} traces`}if(e.chroms){let t=e.chroms;return t.length<=3?t.join(`, `):`${t.length} chroms`}return`all`}var Mt=[`H3K27ac`,`H3K4me3`,`H3K27me3`,`H3K9me3`,`LaminB1`,`H3K36me3`,`H3K4me1`,`H3K9ac`,`CTCF`,`ATAC`];function Nt(e,t=6){let n=new Map(e.map(e=>[e.toLowerCase(),e])),r=Mt.map(e=>n.get(e.toLowerCase())).filter(e=>!!e).slice(0,t);return r.length?r:e.slice(0,t)}function Pt(e,t,n,r=0){let i=0,a=e.length-1;if(a<0)return-1;for(;i<a;){let t=i+a+1>>1;e[t]<=n?i=t:a=t-1}return n>=e[i]-r&&n<t[i]+r?i:i+1<e.length&&n>=e[i+1]-r?i+1:-1}var Ft={matrix:200,track:44,intervals:22};function It(e,t,n=1/0){let r=e.map(e=>e.height??(e.kind===`matrix`?null:Ft[e.kind])),i=r.filter(e=>e===null).length,a=t-e.length-r.reduce((e,t)=>e+(t??0),0),o=i?Math.max(120,Math.min(Math.ceil(n/2),Math.floor(a/i))):0;return r.map(e=>e??o)}function Lt(e){let t=new Set(e.map(e=>e.id)),n=e.length+1;for(;t.has(`r${n}`);)n++;return`r${n}`}function Rt(e,t){return[...e,{...t,id:Lt(e)}]}function zt(e,t){return e.filter(e=>e.id!==t)}function Bt(e,t,n){let r=e.findIndex(e=>e.id===t);if(r<0)return e;let i=Math.max(0,Math.min(e.length-1,r+n));if(r===i)return e;let a=[...e],[o]=a.splice(r,1);return a.splice(i,0,o),a}function Vt(e,t,n){return e.map(e=>e.id===t?{...e,...n}:e)}function Ht(e,t,n){return Vt(e,t,{height:Math.round(Math.max(16,Math.min(900,n)))})}function Ut(e,t){if(typeof t==`boolean`)return e===`balance`||e===`flip`?{[e]:t}:null;let n=t.trim(),r=e=>Number.isFinite(e)&&e>0?e:NaN;switch(e){case`source`:return n?{source:n,resolution:null}:null;case`track`:case`key`:return n?{[e]:n}:null;case`agg`:return n===`mean`||n===`median`||n===`max`?{agg:n}:null;case`stat`:return n===`median`||n===`mean`||n===`contact`?{stat:n}:null;case`resolution`:case`threshold`:{if(!n)return{[e]:null};let t=r(Number(n));return Number.isNaN(t)?null:{[e]:t}}case`height`:{if(!n)return{height:null};let e=r(Number(n));return Number.isNaN(e)?null:{height:Math.round(Math.max(16,Math.min(900,e)))}}case`maxDist`:if(!n)return{maxDist:null};try{let e=Ct(n);return e>0?{maxDist:e}:null}catch{return null}default:return null}}function Wt(e,t,n,r){let i=Ut(n,r);return i?Vt(e,t,i):e}function Gt(e,t){if(!e)return[];let n=[],r=e.contact_maps??[],i=r.find(e=>!e.per_cell),a=r.find(e=>e.per_cell);i&&(n=Rt(n,{kind:`matrix`,source:i.key})),a&&(n=Rt(n,{kind:`matrix`,source:a.key})),e.has_coords!==!1&&e.n_spots>0&&(n=Rt(n,{kind:`matrix`,source:`distance`}));for(let t of e.intervals??[])n=Rt(n,{kind:`intervals`,key:t.key});let o=(e.tracks??[]).map(e=>e.name),s=new Set(o),c=(t??[]).filter(e=>s.has(e));for(let e of c.length?c:Nt(o))n=Rt(n,{kind:`track`,track:e});return n}function Kt(e){if(!Array.isArray(e))return null;let t=[];for(let n of e){if(!n||typeof n!=`object`)return null;let e=n;if(typeof e.id!=`string`||e.kind!==`matrix`&&e.kind!==`track`&&e.kind!==`intervals`)return null;let r={id:e.id,kind:e.kind};typeof e.height==`number`&&e.height>=16&&e.height<=900&&(r.height=e.height),typeof e.source==`string`&&(r.source=e.source),typeof e.resolution==`number`&&e.resolution>0&&(r.resolution=e.resolution),typeof e.balance==`boolean`&&(r.balance=e.balance),(e.stat===`median`||e.stat===`mean`||e.stat===`contact`)&&(r.stat=e.stat),typeof e.threshold==`number`&&e.threshold>0&&(r.threshold=e.threshold),typeof e.maxDist==`number`&&e.maxDist>0&&(r.maxDist=e.maxDist),typeof e.flip==`boolean`&&(r.flip=e.flip),typeof e.track==`string`&&(r.track=e.track),typeof e.key==`string`&&(r.key=e.key);let i=st(e.scope,!0);i&&i.kind!==`view`&&(r.scope=i),(e.agg===`mean`||e.agg===`median`||e.agg===`max`)&&(r.agg=e.agg),t.push(r)}return new Set(t.map(e=>e.id)).size===t.length?t:null}function qt(e,t,n={}){let r=Array.isArray(t)?t:[];return e.map((e,t)=>{let i=r[t]??{};if(e.scope||`scope`in i)return e.kind===`track`&&!e.agg&&n.agg?{...e,agg:n.agg}:e;let a;typeof i.group==`string`&&i.group?a={kind:`group`,group:i.group}:(e.kind===`matrix`&&e.source===`distance`&&i.followFocus===!1||e.kind===`track`&&n.tracksCellOnly===!1)&&(a={kind:`all`});let o={...e};return a&&(o.scope=a),e.kind===`track`&&!e.agg&&n.agg&&(o.agg=n.agg),o})}function Jt(e,t,n){return e.map(e=>{if(e.id!==t)return e;let{scope:r,...i}=e;return n.kind===`view`?i:{...i,scope:n}})}function Yt(e,t,n){return!e||!(t>0)||!(n>0)?1:e/t/2/n}function Xt(e,t,n){if(t<0||t>n.height)return null;let r=(n.flip?t:n.height-t)*n.k,i=n.start+(e-r)*n.bpPerPx,a=n.start+(e+r)*n.bpPerPx;return n.maxDist!==null&&a-i>n.maxDist*(1+1e-9)?null:[i,a]}function Zt(e,t,n,r,i){let a=Xt(e,t,n);if(!a)return null;let o=me(r,i,a[0]),s=me(r,i,a[1]);return o<0||s<0?null:[o,s]}var Qt=4;function $t(e,t,n,r,i,a){let o=r.length,s=new Uint8ClampedArray(4*e*t),c=new Int32Array(e*Qt+1);for(let e=0;e<c.length;e++)c[e]=me(r,i,n.start+(e+.5)/Qt*n.bpPerPx);for(let r=0;r<t;r++){let i=r+.5,l=(n.flip?i:t-i)*n.k;if(n.maxDist!==null&&2*l*n.bpPerPx>n.maxDist*(1+1e-9))continue;let u=4*e*r,d=Math.max(0,Math.ceil(l-.5)),f=Math.min(e,Math.floor(e-l-.5)+1);for(let e=d;e<f;e++){let t=e+.5,n=Math.floor((t-l)*Qt),r=Math.floor((t+l)*Qt);if(n<0||r>=c.length)continue;let i=c[n],d=c[r];if(i<0||d<0)continue;let f=4*(i*o+d),p=u+4*e;s[p]=a[f],s[p+1]=a[f+1],s[p+2]=a[f+2],s[p+3]=255}}return s}var en=[`tabs`,`columns`,`rows`,`grid`],tn=[`3d`,`embedding`,`genome`,`matrix`,`stats`],nn={"3d":`3D`,embedding:`Embedding`,genome:`Genome`,matrix:`Matrix`,stats:`Stats`},rn=.1,an=(e,t)=>({id:e,type:t,embeddingKey:null,dims:[0,1]});function on(e){let t=typeof e==`boolean`?{hasEmbeddings:e,hasCoords:!0,hasTracks:!1}:e,n=(e,t,n)=>({layout:`columns`,panes:[an(`P1`,e),an(`P2`,t)],activePane:`P1`,sizes:n,maximized:null});return t.hasCoords?t.hasEmbeddings?n(`3d`,`embedding`,[.6,.4]):t.hasTracks||t.hasContactMaps?n(`3d`,`genome`,[.5,.5]):n(`3d`,`matrix`,[.55,.45]):t.hasEmbeddings?n(`matrix`,`embedding`,[.55,.45]):{layout:`columns`,panes:[an(`P1`,`matrix`)],activePane:`P1`,sizes:[1],maximized:null}}var sn=e=>e.panes.map(e=>e.type).join(`,`);function cn(e){for(let t of[`umap`,`tsne`,`pca`]){let n=e.find(e=>e.method===t);if(n)return n.key}return e[0]?.key??null}function ln(e,t){if(t<=0)return[];let n=e.length===t&&e.every(e=>Number.isFinite(e)&&e>0)?[...e]:Array(t).fill(1/t),r=n.reduce((e,t)=>e+t,0);if(n=n.map(e=>e/r),t*.1>=1)return Array(t).fill(1/t);for(let e=0;e<4;e++){let e=n.map(e=>e<rn),t=n.reduce((t,n,r)=>t+(e[r]?rn-n:0),0);if(t<=1e-12)break;let r=n.reduce((t,n,r)=>t+(e[r]?0:n-rn),0);n=n.map((n,i)=>e[i]?rn:n-(n-rn)/r*t)}return n}function un(e){let t=new Set(e.panes.map(e=>e.id)),n=e.panes.length+1;for(;t.has(`P${n}`);)n++;return`P${n}`}function dn(e,t,n={}){let r=un(e),i=e.panes.length+1,a=ln([...e.sizes.map(e=>e*(1-1/i)),1/i],i);return{...e,panes:[...e.panes,{...an(r,t),...n}],sizes:a,activePane:r,maximized:null}}function fn(e,t,n){return mn(e,t,{kind:`cell`,cell:n})}function pn(e,t,n){return mn(e,t,{kind:`group`,group:n})}function mn(e,t,n){let r=dn(e,t,{scope:n});return(r.layout===`columns`||r.layout===`rows`)&&r.panes.length>3?{...r,layout:`grid`}:r}function hn(e,t,n){return Sn(e,t,{scope:n})}var gn=e=>e?.scope?.kind===`cell`?e.scope.cell:null,_n=e=>e?.scope?.kind===`group`?e.scope.group:null;function vn(e,t){let n=!1,r=e=>e?.kind===`group`&&e.group===t,i=e.panes.map(e=>{let i=e;if(r(i.scope)&&(i={...i,scope:it}),i.compareGroups?.includes(t)&&(i={...i,compareGroups:i.compareGroups.filter(e=>e!==t)}),i.genomeRows&&Object.values(i.genomeRows).some(e=>e.some(e=>r(e.scope)))){let e={};for(let[t,n]of Object.entries(i.genomeRows))e[t]=n.map(e=>r(e.scope)?{...e,scope:{kind:`view`}}:e);i={...i,genomeRows:e}}return i!==e&&(n=!0),i});return n?{...e,panes:i}:e}function yn(e,t){let n=_n,r=e=>n(e)!==null&&!t(n(e))||(e.compareGroups??[]).some(e=>!t(e));return e.panes.some(r)?{...e,panes:e.panes.map(e=>r(e)?{...e,scope:n(e)!==null&&!t(n(e))?it:e.scope,compareGroups:(e.compareGroups??[]).filter(t)}:e)}:e}function bn(e,t){let n=e=>gn(e)!==null&&!t.has(gn(e));return e.panes.some(n)?{...e,panes:e.panes.map(e=>n(e)?{...e,scope:it}:e)}:e}function xn(e,t){let n=e.panes.findIndex(e=>e.id===t);if(n<0||e.panes.length<=1)return e;let r=e.panes.filter(e=>e.id!==t),i=ln(e.sizes.filter((e,t)=>t!==n),r.length),a=e.activePane===t?r[Math.max(0,n-1)].id:e.activePane;return{...e,panes:r,sizes:i,activePane:a,maximized:e.maximized===t?null:e.maximized}}function Sn(e,t,n){return{...e,panes:e.panes.map(e=>e.id===t?{...e,...n}:e)}}function Cn(e,t,n){return Sn(e,t,{type:n})}function wn(e,t){return{...e,layout:t,maximized:null}}function Tn(e,t,n){let r=ln(e.sizes,e.panes.length);if(t<0||t>=r.length-1)return e;let i=r.slice(0,t).reduce((e,t)=>e+t,0),a=r[t]+r[t+1],o=Math.min(a-rn,Math.max(rn,n-i));return r[t]=o,r[t+1]=a-o,{...e,sizes:r}}function En(e){let t=st(e.scope);return t&&t.kind!==`view`?t:typeof e.group==`string`&&e.group?{kind:`group`,group:e.group}:e.type===`matrix`&&e.followFocus===!1?{kind:`all`}:typeof e.cell==`string`&&e.cell?{kind:`cell`,cell:e.cell}:it}function Dn(e){let t={},n=En(e);n.kind!==`focus`&&(t.scope=n),Array.isArray(e.compareGroups)&&e.compareGroups.every(e=>typeof e==`string`)&&(t.compareGroups=[...e.compareGroups]);let r=e.agg===`mean`||e.agg===`median`||e.agg===`max`?e.agg:void 0;if(r&&(t.agg=r),e.genomeRows&&typeof e.genomeRows==`object`&&!Array.isArray(e.genomeRows)){let n={};for(let[t,i]of Object.entries(e.genomeRows)){let a=Kt(i);a&&(n[t]=qt(a,i,{tracksCellOnly:typeof e.followFocus==`boolean`?e.followFocus:void 0,agg:r}))}Object.keys(n).length&&(t.genomeRows=n)}return Array.isArray(e.tracks)&&e.tracks.every(e=>typeof e==`string`)&&(t.tracks=e.tracks),typeof e.source==`string`&&(t.source=e.source),typeof e.balance==`boolean`&&(t.balance=e.balance),typeof e.resolution==`number`&&e.resolution>0&&(t.resolution=e.resolution),(e.stat===`median`||e.stat===`mean`||e.stat===`contact`)&&(t.stat=e.stat),typeof e.threshold==`number`&&e.threshold>0&&(t.threshold=e.threshold),(e.statsKind===`rg`||e.statsKind===`scaling`||e.statsKind===`hist`||e.statsKind===`scatter`)&&(t.statsKind=e.statsKind),typeof e.fieldX==`string`&&(t.fieldX=e.fieldX),typeof e.fieldY==`string`&&(t.fieldY=e.fieldY),(e.chromScope===`all`||e.chromScope===`locus`)&&(t.chromScope=e.chromScope),t}function On(e){if(!e||typeof e!=`object`)return null;let t=e;if(!en.includes(t.layout)||!Array.isArray(t.panes)||!t.panes.length)return null;let n=[];for(let e of t.panes){let t=e&&e.type===`tracks`?{...e,type:`genome`}:e;if(!t||typeof t.id!=`string`||!tn.includes(t.type))return null;let r=Array.isArray(t.dims)&&t.dims.length===2&&t.dims.every(e=>Number.isInteger(e)&&e>=0)?[t.dims[0],t.dims[1]]:[0,1];n.push({...Dn(t),id:t.id,type:t.type,embeddingKey:typeof t.embeddingKey==`string`?t.embeddingKey:null,dims:r})}if(new Set(n.map(e=>e.id)).size!==n.length)return null;let r=n.some(e=>e.id===t.activePane)?t.activePane:n[0].id,i=n.some(e=>e.id===t.maximized)?t.maximized:null;return{layout:t.layout,panes:n,activePane:r,sizes:ln(Array.isArray(t.sizes)?t.sizes:[],n.length),maximized:i}}function kn(e,t){let n=e.target?.tagName;return n===`INPUT`||n===`TEXTAREA`||n===`SELECT`?!1:e.key===`Escape`?(t.hasPick?t.clearPick():t.clearFocus(),!0):e.key===`ArrowRight`||e.key===`ArrowDown`?(t.step(1),!0):e.key===`ArrowLeft`||e.key===`ArrowUp`?(t.step(-1),!0):!1}var An=1,jn=()=>`L${An++}`,Mn={focusCell:null,focusGroup:null,selection:null,hiddenChroms:[],contextOpacity:.15,overviewColor:`cell`,cellField:null,hiddenCategories:[],cellSort:`id`,hiddenPointSets:[],hiddenLabels:{},pointSize:7,maxBond:`auto`,locus:null};function Nn(e){return!!e&&e.has_coords!==!1&&e.n_spots>0}function Pn(e){let t=(e?.cell_fields??[]).filter(e=>e.kind===`category`);return t.find(e=>e.name===`cell_type`)??t.find(e=>/type|cluster/i.test(e.name))??null}function Fn(e){let t=Pn(e);return t?{...Mn,overviewColor:`field`,cellField:t.name}:Mn}var In=(e,t)=>`${e}\u0000${t}`,Ln=`uchrom.browser.workspace`,Rn=`uchrom.browser.groups`;function zn(){try{let e=typeof localStorage<`u`?localStorage.getItem(Rn):null;return e?nt(JSON.parse(e)):{}}catch{return{}}}function Bn(e){try{localStorage.setItem(Rn,JSON.stringify(e))}catch{}}function Vn(){try{localStorage.removeItem(`uchrom.browser.ui`);let e=typeof localStorage<`u`?localStorage.getItem(Ln):null;return e?On(JSON.parse(e)):null}catch{return null}}function Hn(e){try{localStorage.setItem(Ln,JSON.stringify(e))}catch{}}function Un(e){let t=e.datasets.find(t=>t.id===e.activeDatasetId)?.name;return t&&e.savedGroups[t]||Wn}var Wn=[];function Gn(e){let t=U(e);return!e.activeDatasetId||!t.cellField?null:e.cellValues[In(e.activeDatasetId,t.cellField)]??null}function Kn(e){let t=e.activeDatasetId&&e.cells[e.activeDatasetId]||[],n=U(e),r=Gn(e);if(n.overviewColor!==`field`||n.cellSort!==`value`||!r)return t;let i=(e.datasets?.find(t=>t.id===e.activeDatasetId)?.cell_fields?.find(e=>e.name===n.cellField)?.categories??[]).map(e=>e.value),a=new Map(i.map((e,t)=>[e,-t]));for(let e of r.values())typeof e==`string`&&!a.has(e)&&a.set(e,-a.size);let o=e=>{let t=r.get(e.cell_id);return typeof t==`string`?a.get(t)??-1/0:typeof t==`number`&&Number.isFinite(t)?t:-1/0};return t.map((e,t)=>({c:e,i:t})).sort((e,t)=>o(t.c)-o(e.c)||e.i-t.i).map(e=>e.c)}function U(e){return e.activeDatasetId&&e.views[e.activeDatasetId]||Mn}var qn=(e,t,n)=>e.map(e=>e.id===t?{...e,...n}:e),Jn=Vn(),Yn=zn(),W=Ue((e,t)=>{let n=(n,r={})=>{let i=t(),a=i.activeDatasetId;a&&e({views:{...i.views,[a]:{...U(i),...n}},...r})};return{datasets:[],activeDatasetId:null,layers:[],selectedLayerId:null,pick:null,status:null,error:null,resetViewToken:0,flyToken:0,views:{},cells:{},cellValues:{},pointSets:{},setDatasets(n){let r=t();e({datasets:n});for(let e of n)r.layers.some(t=>t.datasetId===e.id)||t().addDataset(e);!t().activeDatasetId&&n.length&&e({activeDatasetId:n[0].id})},addDataset(n){let r=t();if(e({datasets:r.datasets.some(e=>e.id===n.id)?r.datasets.map(e=>e.id===n.id?n:e):[...r.datasets,n],activeDatasetId:n.id}),t().views[n.id]||e({views:{...t().views,[n.id]:Fn(n)}}),!t().layers.some(e=>e.datasetId===n.id&&e.parentId===null)){let r=n.trace_mode?{mode:`tube`}:{};e({selectedLayerId:t().addLayer({datasetId:n.id,parentId:null,name:n.name,filter:{},style:r}),resetViewToken:t().resetViewToken+1})}},removeDataset(n){let r=t(),i=r.layers.filter(e=>e.datasetId!==n),a=r.datasets.filter(e=>e.id!==n);e({datasets:a,layers:i,activeDatasetId:r.activeDatasetId===n?a[0]?.id??null:r.activeDatasetId,selectedLayerId:i.some(e=>e.id===r.selectedLayerId)?r.selectedLayerId:null,pick:null})},setActiveDataset(n){e({activeDatasetId:n,selectedLayerId:t().layers.find(e=>e.datasetId===n&&e.parentId===null)?.id??null,pick:null})},addLayer({datasetId:n,parentId:r,name:i,filter:a,style:o}){let s=jn(),c=t().layers,l={id:s,name:bt(c.filter(e=>e.datasetId===n),i),datasetId:n,parentId:r,filter:a,visible:!0,style:{...gt,...o},geometry:null,loading:!1,error:null};return e({layers:[...r?qn(c,r,{visible:!1}):c,l],selectedLayerId:s}),s},removeLayer(n){let r=t(),i=vt(r.layers,n);e({layers:i,selectedLayerId:i.some(e=>e.id===r.selectedLayerId)?r.selectedLayerId:null,pick:r.pick&&(xt(r.pick)||i.some(e=>e.id===r.pick.layerId))?r.pick:null})},renameLayer(n,r){let i=r.trim();i&&e({layers:qn(t().layers,n,{name:i})})},setVisible(n,r){e({layers:qn(t().layers,n,{visible:r})})},setStyle(n,r){e({layers:t().layers.map(e=>e.id===n?{...e,style:{...e.style,...r}}:e)})},setLoading(n){e({layers:qn(t().layers,n,{loading:!0,error:null})})},setGeometry(n,r){let i=t(),a=i.layers.find(e=>e.id===n),o=!!a&&a.parentId!==null&&a.geometry===null;e({layers:qn(i.layers,n,{geometry:r,loading:!1,error:null}),...o?{resetViewToken:i.resetViewToken+1}:{}})},setLayerError(n,r){e({layers:qn(t().layers,n,{loading:!1,error:r})})},selectLayer(t){e({selectedLayerId:t})},setPick(t){e({pick:t})},setStatus(t){e({status:t})},setError(t){e({error:t})},workspace:Jn??on(!1),workspaceTouched:Jn!==null,ensureDefaultWorkspace(n){let r=t();if(r.workspaceTouched)return;let i=on(n);sn(i)!==sn(r.workspace)&&e({workspace:i})},setWorkspace(n){let r=n(t().workspace);r!==t().workspace&&(e({workspace:r,workspaceTouched:!0}),Hn(r))},openCellView(e){let n=t().datasets.find(e=>e.id===t().activeDatasetId);t().setWorkspace(t=>fn(t,Nn(n)?`3d`:`genome`,e))},resetView(){e({resetViewToken:t().resetViewToken+1})},setCells(n,r){e({cells:{...t().cells,[n]:r}})},focusCell(e){let r=t(),i=U(r);(i.focusCell!==e||e===null&&i.focusGroup!==null)&&n({focusCell:e,focusGroup:null},{pick:null,flyToken:r.flyToken+1})},savedGroups:Yn,focusGroup(e){let r=t(),i=U(r);(i.focusGroup!==e||i.focusCell!==null)&&n({focusGroup:e,focusCell:null},{pick:null,flyToken:r.flyToken+1})},setSelection(e){let r=t(),i=U(r),a=e?e.id:i.focusGroup===i.selection?.id?null:i.focusGroup;n({selection:e,focusGroup:a,focusCell:e?null:i.focusCell},{pick:null,flyToken:r.flyToken+1})},saveSelection(r){let i=t(),a=U(i),o=i.datasets.find(e=>e.id===i.activeDatasetId);if(!o||!a.selection)return;let s=i.savedGroups[o.name]??[],c=s.find(e=>e.id===a.selection.id),l={id:a.selection.id,name:r?.trim()||c?.name||Qe(s),color:c?.color??Ze(s.length),cells:a.selection.cells},u={...i.savedGroups,[o.name]:$e(s,l)};e({savedGroups:u}),Bn(u),n({selection:null,focusGroup:l.id,focusCell:null})},renameSavedGroup(n,r){let i=t(),a=i.datasets.find(e=>e.id===i.activeDatasetId);if(!a)return;let o={...i.savedGroups,[a.name]:et(i.savedGroups[a.name]??[],n,r)};e({savedGroups:o}),Bn(o)},deleteSavedGroup(r){let i=t(),a=i.datasets.find(e=>e.id===i.activeDatasetId);if(!a)return;let o={...i.savedGroups,[a.name]:tt(i.savedGroups[a.name]??[],r)};e({savedGroups:o}),Bn(o),U(i).focusGroup===r&&n({focusGroup:null}),t().setWorkspace(e=>vn(e,r))},stepCell(e){let n=t(),r=Kn(n);if(!r.length)return;let i=r.findIndex(e=>e.cell_id===U(n).focusCell),a=i<0?e>0?0:r.length-1:(i+e+r.length)%r.length;t().focusCell(r[a].cell_id)},toggleChrom(e){let r=new Set(U(t()).hiddenChroms);r.has(e)?r.delete(e):r.add(e),n({hiddenChroms:[...r]})},setHiddenChroms(e){n({hiddenChroms:[...e]})},setContextOpacity(e){n({contextOpacity:e})},setOverviewColor(e){n({overviewColor:e})},setCellField(e){let r=U(t()),i=e===r.cellField?r.hiddenCategories:[];n(e?{cellField:e,overviewColor:`field`,hiddenCategories:i}:{cellField:null,hiddenCategories:i})},toggleCategory(e){let r=new Set(U(t()).hiddenCategories);r.has(e)?r.delete(e):r.add(e),n({hiddenCategories:[...r]})},setHiddenCategories(e){n({hiddenCategories:[...e]})},setCellSort(e){n({cellSort:e})},setCellValues(n,r,i){e({cellValues:{...t().cellValues,[In(n,r)]:i}})},setPointSet(n,r){let i=t().pointSets;e({pointSets:{...i,[n]:{...i[n]??{},[r.name]:r}}})},togglePointSet(e){let r=new Set(U(t()).hiddenPointSets);r.has(e)?r.delete(e):r.add(e),n({hiddenPointSets:[...r]})},toggleLabel(e,r){let i=U(t()),a=new Set(i.hiddenLabels[e]??[]);a.has(r)?a.delete(r):a.add(r),n({hiddenLabels:{...i.hiddenLabels,[e]:[...a]}})},setHiddenLabels(e,r){let i=U(t());n({hiddenLabels:{...i.hiddenLabels,[e]:[...r]}})},setPointSize(e){n({pointSize:e})},setMaxBond(e){n({maxBond:e})},setLocus(e){let r=U(t()).locus;r&&r.chrom===e.chrom&&r.start===e.start&&r.end===e.end||n({locus:e})}}});Oe((e,t)=>{let n=W.getState(),r=n.datasets.find(t=>t.id===e),i=r?(n.savedGroups[r.name]??[]).find(e=>e.id===t):void 0;if(i)return i.cells;let a=n.views[e]?.selection;return a&&a.id===t?a.cells:null});function Xn(e){if(e==null||!Number.isFinite(e))return`—`;if(Number.isInteger(e))return e.toLocaleString(`en-US`);let t=Math.abs(e);return t>=100?Math.round(e).toLocaleString(`en-US`):t>=1?(+e.toFixed(2)).toString():(+e.toPrecision(3)).toString()}function Zn(e){return typeof e==`string`?e:Xn(e)}function Qn(e){let t=e=>e.min===0&&e.max===1;return e.filter(e=>!/(^|_)id$/i.test(e.name)).map((e,t)=>({f:e,i:t})).sort((e,n)=>Number(t(e.f))-Number(t(n.f))||e.i-n.i).map(e=>e.f)}function $n(e){return(e.includes(`.`)?e.slice(e.indexOf(`.`)+1):e).replace(/_um2$/,` (µm²)`).replace(/_um$/,` (µm)`).replace(/_/g,` `)}var er=o((e=>{var t=u(),n=Symbol.for(`react.element`),r=Symbol.for(`react.fragment`),i=Object.prototype.hasOwnProperty,a=t.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,o={key:!0,ref:!0,__self:!0,__source:!0};function s(e,t,r){var s,c={},l=null,u=null;for(s in r!==void 0&&(l=``+r),t.key!==void 0&&(l=``+t.key),t.ref!==void 0&&(u=t.ref),t)i.call(t,s)&&!o.hasOwnProperty(s)&&(c[s]=t[s]);if(e&&e.defaultProps)for(s in t=e.defaultProps,t)c[s]===void 0&&(c[s]=t[s]);return{$$typeof:n,type:e,key:l,ref:u,props:c,_owner:a.current}}e.Fragment=r,e.jsx=s,e.jsxs=s})),G=o(((e,t)=>{t.exports=er()}))(),tr=new Map,nr=12;function rr(e){let t=[],n=[];for(let[r,i]of Object.entries(e))r.startsWith(`rna.`)?typeof i==`number`&&Number.isFinite(i)&&n.push({name:r,label:r.slice(4),value:i}):/(^|_)id$/i.test(r)||t.push([r,i]);return n.sort((e,t)=>t.value-e.value||e.label.localeCompare(t.label)),{attrs:t,rna:n}}function ir(){let e=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId));if(!e)return null;let t=e.has_coords!==!1&&e.n_spots>0,n=[e.n_cells>1?`${e.n_cells.toLocaleString(`en-US`)} cells`:null,t?`${e.n_traces.toLocaleString(`en-US`)} traces`:null,t?`${e.n_spots.toLocaleString(`en-US`)} spots`:null,e.chroms.length?`${e.chroms.length} chroms`:null,e.contact_maps?.length?`${e.contact_maps.length} contact maps`:null,t&&e.xyz_unit?e.xyz_unit:null].filter(Boolean);return(0,G.jsxs)(`section`,{className:`cell-info`,children:[(0,G.jsx)(`h2`,{children:e.name}),(0,G.jsx)(`div`,{className:`muted small`,children:n.join(` · `)}),e.n_cells>1&&(0,G.jsx)(`div`,{className:`muted small`,children:`No cell focused — pick one in the list or any view.`})]})}function ar(){let e=W(e=>e.activeDatasetId),t=!!W(e=>e.datasets.find(t=>t.id===e.activeDatasetId))?.cell_fields?.length,n=W(U),r=W(e=>e.setCellField),[i,a]=(0,g.useState)(null),[o,s]=(0,g.useState)(null),[c,l]=(0,g.useState)(!1),u=n.focusCell;if((0,g.useEffect)(()=>{if(a(null),s(null),!e||!u||!t)return;let n=`${e}\u0000${u}`,r=tr.get(n);if(r)return a(r);let i=!0;return Se(e,u).then(e=>{tr.set(n,e),i&&a(e)}).catch(e=>i&&s(e.message)),()=>{i=!1}},[e,u,t]),!u)return(0,G.jsx)(ir,{});if(!t)return null;let{attrs:d,rna:f}=i?rr(i.fields):{attrs:[],rna:[]},p=c?f:f.slice(0,nr),m=f.length?Math.max(1e-9,f[0].value):1;return(0,G.jsxs)(`section`,{className:`cell-info`,children:[(0,G.jsxs)(`h2`,{children:[`Cell `,u]}),o&&(0,G.jsx)(`div`,{className:`error`,children:o}),!i&&!o&&(0,G.jsx)(`div`,{className:`muted small`,children:`loading…`}),d.length>0&&(0,G.jsx)(`dl`,{className:`stats`,children:d.map(([e,t])=>(0,G.jsxs)(`div`,{className:`kv`,children:[(0,G.jsx)(`dt`,{children:$n(e)}),(0,G.jsx)(`dd`,{children:typeof t==`number`?Xn(t):t??`—`})]},e))}),f.length>0&&(0,G.jsxs)(G.Fragment,{children:[(0,G.jsx)(`div`,{className:`muted small`,children:`RNA counts · click a gene to colour all cells by it`}),(0,G.jsx)(`ul`,{className:`bars`,children:p.map(e=>(0,G.jsxs)(`li`,{onClick:()=>r(e.name),title:`Colour all cells by ${e.label}`,children:[(0,G.jsx)(`span`,{className:`bar-label`,children:e.label}),(0,G.jsx)(`span`,{className:`bar-track`,children:(0,G.jsx)(`span`,{className:`bar-fill`,style:{width:`${100*e.value/m}%`}})}),(0,G.jsx)(`span`,{className:`bar-value`,children:Xn(e.value)})]},e.name))}),f.length>nr&&(0,G.jsx)(`button`,{className:`link`,onClick:()=>l(!c),children:c?`show top`:`show all ${f.length}`})]})]})}function or(){return W(e=>{let t=U(e);return t.overviewColor!==`field`||!t.cellField?null:e.datasets.find(t=>t.id===e.activeDatasetId)?.cell_fields?.find(e=>e.name===t.cellField)??null})}function sr(){let e=or(),t=W(Gn),n=W(e=>U(e).hiddenCategories);return(0,g.useMemo)(()=>{if(!e)return{field:null};let r=t??void 0;return e.kind===`category`?{field:e,cellValues:r,categories:j(e,n,t?.values())}:{field:e,cellValues:r,fieldRange:t?D(t.values()):void 0}},[e,t,n])}var cr=new Set;function lr(e,t){let n=In(e,t);cr.has(n)||W.getState().cellValues[n]||(cr.add(n),xe(e,t).then(n=>{let r=new Map;n.cell_ids.forEach((e,t)=>r.set(String(e),n.values[t])),W.getState().setCellValues(e,t,r)}).catch(e=>{cr.delete(n),W.getState().setError(`Cannot load ${t}: ${e.message}`)}))}function ur(){let e=W(e=>e.datasets),t=W(e=>e.activeDatasetId),n=W(U);(0,g.useEffect)(()=>{let{setPointSet:t,setError:n}=W.getState();for(let r of e)for(let e of r.point_sets??[]){let i=`points\u0000${r.id}\u0000${e.name}`;cr.has(i)||(cr.add(i),Ce(r.id,e.name).then(e=>t(r.id,e)).catch(t=>n(`Cannot load point set ${e.name}: ${t.message}`)))}},[e]);let r=W(e=>Pn(e.datasets.find(t=>t.id===e.activeDatasetId))?.name??null);(0,g.useEffect)(()=>{if(t)for(let e of new Set([n.cellField,r]))e&&lr(t,e)},[t,n.cellField,r])}var dr=[];function fr(){let e=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)?.cell_fields)??dr;return(0,g.useMemo)(()=>e.filter(e=>e.kind===`category`),[e])}function pr(e){let t=W(e=>e.activeDatasetId),n=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)?.cell_fields)??dr,r=W(Un),i=W(e=>U(e).selection),a=W(e=>e.cellValues),o=e.join(``);return(0,g.useEffect)(()=>{if(t)for(let n of e){let e=n?Ke(n):null;e&&lr(t,e.field)}},[t,o]),(0,g.useMemo)(()=>e.map(e=>e&&t?ft(e,{fields:n,saved:r,selection:i,values:e=>a[In(t,e)]}):null),[o,t,n,r,i,a])}function mr(e){return pr([e])[0]}function hr(){let e=W(e=>U(e).focusCell),t=W(e=>U(e).focusGroup);return(0,g.useMemo)(()=>({focusCell:e,focusGroup:t}),[e,t])}function gr(e){let t=hr(),n=JSON.stringify(e?.scope??null);return(0,g.useMemo)(()=>at(e?.scope,t),[n,t])}function _r(e,t){let n=hr(),r=JSON.stringify(e??null);return(0,g.useMemo)(()=>ot(e,t,n),[r,t,n])}function vr(e){let t=mr(e.kind===`group`?e.group:null);return(0,g.useMemo)(()=>e.kind===`all`?null:e.kind===`cell`?new Set([e.cell]):new Set(t?.cells??[]),[e,t])}function yr(){let e=fr(),t=W(Un);return(0,g.useMemo)(()=>({fields:e.map(e=>({field:e,refs:(e.categories??[]).map(t=>Ge(e.name,t.value))})),saved:t.map(e=>e.id)}),[e,t])}function br(e){let[t,n]=(0,g.useState)({w:0,h:0});return(0,g.useEffect)(()=>{let t=e.current;if(!t)return;let r=()=>n({w:t.clientWidth,h:t.clientHeight}),i=new ResizeObserver(r);return i.observe(t),r(),()=>i.disconnect()},[e]),t}function xr(e,t,n){let r=window.devicePixelRatio||1;e.width=Math.max(1,Math.round(t*r)),e.height=Math.max(1,Math.round(n*r)),e.style.width=`${t}px`,e.style.height=`${n}px`;let i=e.getContext(`2d`);return i?(i.setTransform(r,0,0,r,0,0),i.clearRect(0,0,t,n),i):null}var Sr=22,Cr=12;function wr(){let e=W(e=>e.activeDatasetId&&e.cells[e.activeDatasetId]||null),t=W(U),n=W(e=>e.activeDatasetId),r=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)),i=W(e=>e.cells),a=W(e=>e.views),o=W(e=>e.cellValues),s=W(e=>e.datasets),c=(0,g.useMemo)(()=>Kn({activeDatasetId:n,cells:i,views:a,cellValues:o,datasets:s}),[n,i,a,o,s]),l=W(e=>e.focusCell),u=W(e=>e.setCellSort),d=W(e=>e.openCellView),f=sr(),[p,m]=(0,g.useState)(``),h=(0,g.useRef)(null),{h:_}=br(h),[v,y]=(0,g.useState)(0),b=t.overviewColor===`field`&&!!t.cellField,x=f.cellValues,S=mr(t.focusGroup),C=(0,g.useMemo)(()=>S?.cells?new Set(S.cells):null,[S]),w=r?.has_coords!==!1&&(r?.n_spots??0)>0,T=w?null:Pn(r),E=W(e=>n&&T?e.cellValues[In(n,T.name)]:void 0),D=T&&!(b&&t.cellField===T.name)?E:void 0,O=(0,g.useMemo)(()=>{let t=new Map((e??[]).map((e,t)=>[e.cell_id,t+1])),n=p.trim().toLowerCase(),r=c.map(e=>({...e,index:t.get(e.cell_id)??0}));if(!n)return r;let i=e=>{let t=E?.get(e)??(f.categories?x?.get(e):void 0);return typeof t==`string`?t.toLowerCase():``};return r.filter(e=>e.cell_id.toLowerCase().includes(n)||i(e.cell_id).includes(n))},[e,c,p,E,x,f.categories]);if((0,g.useEffect)(()=>{let e=h.current;if(!e)return;let n=t.focusCell===null?0:O.findIndex(e=>e.cell_id===t.focusCell)+1;if(n<0)return;let r=n*Sr;r<e.scrollTop?e.scrollTop=r:r+Sr>e.scrollTop+e.clientHeight&&(e.scrollTop=r+Sr-e.clientHeight)},[t.focusCell]),(0,g.useEffect)(()=>{h.current&&(h.current.scrollTop=0),y(0)},[p,n]),!e||e.length<2)return null;let k=Math.max(0,Math.floor(v/Sr)-1-Cr),A=Math.min(O.length,Math.ceil((v+(_||400))/Sr)+Cr),j=O.slice(k,A);return(0,G.jsxs)(`section`,{className:`panel cells`,children:[(0,G.jsxs)(`h2`,{children:[`Cells `,(0,G.jsx)(`span`,{className:`muted`,children:e.length.toLocaleString(`en-US`)}),b&&(0,G.jsxs)(`span`,{className:`cell-sort`,children:[(0,G.jsx)(`button`,{className:t.cellSort===`id`?`active`:``,onClick:()=>u(`id`),title:`Natural id order`,children:`id`}),(0,G.jsxs)(`button`,{className:t.cellSort===`value`?`active`:``,onClick:()=>u(`value`),title:f.categories?`Group by ${$n(t.cellField)}`:`Highest ${$n(t.cellField)} first`,children:[$n(t.cellField),` `,f.categories?``:`↓`]})]})]}),(0,G.jsx)(`input`,{placeholder:T||f.categories?`Search cell id or type…`:`Search cell id…`,value:p,onChange:e=>m(e.target.value)}),(0,G.jsxs)(`ul`,{className:`cell-list`,ref:h,onScroll:e=>y(e.currentTarget.scrollTop),children:[(0,G.jsxs)(`li`,{className:t.focusCell===null?`selected`:``,onClick:()=>l(null),children:[(0,G.jsx)(`span`,{className:`idx`}),`All cells `,p&&(0,G.jsxs)(`span`,{className:`muted`,children:[`· `,O.length.toLocaleString(`en-US`),` match`]})]}),k>0&&(0,G.jsx)(`li`,{className:`spacer`,style:{height:k*Sr},"aria-hidden":!0}),j.map(e=>{let n=x?.get(e.cell_id),r=D?.get(e.cell_id);return(0,G.jsxs)(`li`,{className:`${e.cell_id===t.focusCell?`selected`:``}${C?.has(e.cell_id)?` in-group`:``}`,style:C?.has(e.cell_id)?{boxShadow:`inset 3px 0 0 ${S.color}`}:void 0,onClick:()=>l(e.cell_id),title:`${e.cell_id}${w?` · ${e.n_spots.toLocaleString(`en-US`)} spots`:``}${typeof r==`string`?` · ${r}`:``}${b&&n!==void 0?` · ${$n(t.cellField)}: ${Zn(n)}`:``}`,children:[(0,G.jsx)(`span`,{className:`idx`,children:e.index}),(0,G.jsx)(`span`,{className:`cell-id`,children:e.cell_id}),(0,G.jsx)(`button`,{className:`cell-open`,onClick:t=>{t.stopPropagation(),d(e.cell_id)},title:`Open this cell in a new view`,children:`↗`}),w&&(0,G.jsxs)(`span`,{className:`muted`,children:[` `,e.n_traces,` traces`]}),typeof r==`string`&&(0,G.jsx)(`span`,{className:`muted cell-tag`,children:r}),b&&(f.categories?(0,G.jsxs)(`span`,{className:`cell-value cat`,children:[(0,G.jsx)(`span`,{className:`swatch round`,style:{background:te(M(n,f))}}),x?Zn(n):`…`]}):(0,G.jsx)(`span`,{className:`cell-value`,children:x?Zn(n):`…`}))]},e.cell_id)}),A<O.length&&(0,G.jsx)(`li`,{className:`spacer`,style:{height:(O.length-A)*Sr},"aria-hidden":!0})]}),(0,G.jsx)(`div`,{className:`muted small`,children:`Click a cell here or in the view · ←/→ to step · Esc for all`})]})}function Tr(){let e=yr(),t=W(U),n=W(e=>e.focusGroup),r=W(e=>e.setSelection),i=W(e=>e.saveSelection),a=W(e=>e.renameSavedGroup),o=W(e=>e.deleteSavedGroup),s=W(e=>e.setWorkspace),c=W(e=>Nn(e.datasets.find(t=>t.id===e.activeDatasetId))),l=W(e=>(e.datasets.find(t=>t.id===e.activeDatasetId)?.embeddings?.length??0)>0),u=pr((0,g.useMemo)(()=>[...e.fields.flatMap(e=>e.refs),...e.saved,t.selection?.id??null],[e,t.selection])),d=(0,g.useMemo)(()=>new Map(u.filter(e=>!!e).map(e=>[e.ref,e])),[u]),[f,p]=(0,g.useState)({}),[m,h]=(0,g.useState)(null),[_,v]=(0,g.useState)(``),[y,b]=(0,g.useState)(``),x=e=>n(t.focusGroup===e?null:e),S=e=>s(t=>pn(t,c?`genome`:`matrix`,e)),C=(e,n,r)=>(0,G.jsxs)(`li`,{className:t.focusGroup===n?`selected`:``,onClick:()=>x(n),title:t.focusGroup===n?`Focused — click to release`:`Focus this group in every view`,children:[(0,G.jsx)(`span`,{className:`swatch round`,style:{background:e?.color??`#888`}}),(0,G.jsx)(`span`,{className:`group-name`,children:e?.name??n}),(0,G.jsx)(`span`,{className:`muted small`,children:e?.cells?e.cells.length.toLocaleString(`en-US`):`…`}),r,(0,G.jsx)(`button`,{className:`cell-open`,onClick:e=>{e.stopPropagation(),S(n)},title:`Open a new view aggregating over this group`,children:`↗`})]},n),w=!e.fields.length&&!e.saved.length&&!t.selection;return(0,G.jsxs)(`section`,{className:`panel groups`,children:[(0,G.jsxs)(`h2`,{children:[`Groups`,t.focusGroup&&(0,G.jsx)(`button`,{className:`link`,onClick:()=>n(null),title:`Release the focused group`,children:`clear`})]}),t.selection&&(0,G.jsxs)(`div`,{className:`group-selection`,children:[(0,G.jsxs)(`div`,{children:[(0,G.jsx)(`b`,{children:t.selection.cells.length.toLocaleString(`en-US`)}),` cells selected`]}),(0,G.jsx)(`input`,{placeholder:`name…`,value:y,onChange:e=>b(e.target.value),onKeyDown:e=>{e.key===`Enter`&&(i(y),b(``))}}),(0,G.jsx)(`button`,{onClick:()=>{i(y),b(``)},title:`Keep this selection as a named group`,children:`Save as group`}),(0,G.jsx)(`button`,{onClick:()=>r(null),title:`Discard the selection`,children:`×`})]}),(0,G.jsxs)(`ul`,{className:`group-list`,children:[e.fields.map(({field:e,refs:t},n)=>{let r=f[e.name]??n===0;return(0,G.jsxs)(`li`,{className:`group-field`,children:[(0,G.jsxs)(`div`,{className:`group-field-head`,onClick:()=>p(t=>({...t,[e.name]:!r})),children:[(0,G.jsx)(`span`,{className:`caret`,children:r?`▾`:`▸`}),$n(e.name),` `,(0,G.jsx)(`span`,{className:`muted small`,children:t.length})]}),r&&(0,G.jsx)(`ul`,{children:t.map(e=>C(d.get(e),e))})]},e.name)}),e.saved.length>0&&(0,G.jsxs)(`li`,{className:`group-field`,children:[(0,G.jsx)(`div`,{className:`group-field-head static`,children:`saved`}),(0,G.jsx)(`ul`,{children:e.saved.map(e=>m===e?(0,G.jsx)(`li`,{className:`editing`,children:(0,G.jsx)(`input`,{autoFocus:!0,value:_,onChange:e=>v(e.target.value),onBlur:()=>{a(e,_),h(null)},onKeyDown:e=>{e.key===`Enter`&&e.target.blur(),e.key===`Escape`&&h(null)}})},e):C(d.get(e),e,(0,G.jsxs)(G.Fragment,{children:[(0,G.jsx)(`button`,{className:`cell-open`,onClick:t=>{t.stopPropagation(),v(d.get(e)?.name??``),h(e)},title:`Rename`,children:`✎`}),(0,G.jsx)(`button`,{className:`cell-open`,onClick:t=>{t.stopPropagation(),o(e)},title:`Delete this group`,children:`×`})]})))})]})]}),(0,G.jsxs)(`div`,{className:`muted small`,children:[w?`No groups yet. `:``,l?`Lasso cells in an Embedding view (shift-drag, or the ◌ tool) to make a group.`:`Groups come from categorical cell fields.`]})]})}function Er(e){return e?e.nCells>1?[`cells`,`groups`,`cellInfo`,`colour`]:[`cellInfo`]:[]}function Dr(e,t){if(!e||!t)return[];let n=t.nCells>1?[`pin`]:[];switch(e.type){case`3d`:return t.hasCoords?(n.push(`layers`,`subset`,`style`),t.nChroms>1&&n.push(`chroms`),t.nPointSets>0&&n.push(`points`),n):[...n,`noCoords`];case`genome`:return[...n,`genomeRows`];case`matrix`:return[...n,`matrix`];case`embedding`:return[...n,`embedding`];case`stats`:return[...n,`stats`]}}function Or(e,t){return`${nn[t.type]} · pane ${e.panes.findIndex(e=>e.id===t.id)+1}`}function kr(e){return!e.panes.length||e.panes.some(t=>t.id===e.activePane)?e:{...e,activePane:e.panes[0].id}}function Ar(){let e=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)),t=W(U),n=W(e=>e.toggleChrom),r=W(e=>e.setHiddenChroms),i=W(e=>(e.activeDatasetId&&e.cells[e.activeDatasetId]||[]).length>1),a=W(e=>e.layers.find(t=>t.id===e.selectedLayerId)?.style.colorMode);if(!e||e.chroms.length<2)return null;let o=new Set(t.hiddenChroms),s=(i&&t.focusCell===null?t.overviewColor:a)===`rainbow`,c=e.chroms.map(e=>e.name);return(0,G.jsxs)(`section`,{className:`legend`,children:[(0,G.jsxs)(`h2`,{children:[`Chromosomes`,(0,G.jsxs)(`span`,{className:`legend-actions`,children:[(0,G.jsx)(`button`,{onClick:()=>r([]),disabled:!o.size,children:`all`}),(0,G.jsx)(`button`,{onClick:()=>r(c),disabled:o.size===c.length,children:`none`})]})]}),(0,G.jsx)(`ul`,{className:`legend-list`,children:e.chroms.map(e=>(0,G.jsxs)(`li`,{className:o.has(e.name)?`off`:``,onClick:()=>n(e.name),onDoubleClick:()=>r(c.filter(t=>t!==e.name)),title:`Click to show/hide · double-click to show only this one`,children:[(0,G.jsx)(`span`,{className:`swatch`,style:{background:s?S(e.name):`var(--text-muted)`}}),e.name]},e.name))})]})}function jr(e,t,n,r,i){let a=1/0,o=-1/0,s=1/0,c=-1/0;for(let n=0;n<e.length;n++){let r=e[n],i=t[n];r!==null&&i!==null&&Number.isFinite(r)&&Number.isFinite(i)&&(a=Math.min(a,r),o=Math.max(o,r),s=Math.min(s,i),c=Math.max(c,i))}Number.isFinite(a)||([a,o,s,c]=[0,1,0,1]),o===a&&([a,o]=[a-.5,o+.5]),c===s&&([s,c]=[s-.5,c+.5]);let l=Math.max(1,n-2*i),u=Math.max(1,r-2*i);return{sx:e=>i+(e-a)/(o-a)*l,sy:e=>i+(1-(e-s)/(c-s))*u,bounds:{x0:a,x1:o,y0:s,y1:c}}}function Mr(e,t,n){let r=new Float32Array(2*e.length);for(let i=0;i<e.length;i++){let a=e[i],o=t[i],s=a!==null&&o!==null&&Number.isFinite(a)&&Number.isFinite(o);r[2*i]=s?n.sx(a):NaN,r[2*i+1]=s?n.sy(o):NaN}return r}function Nr(e,t,n,r){let i=-1,a=r*r;for(let r=0;r<e.length/2;r++){let o=e[2*r]-t,s=e[2*r+1]-n,c=o*o+s*s;c<=a&&(a=c,i=r)}return i}var Pr=14;function Fr(e,t){let n=t.embeddingKey&&e.some(e=>e.key===t.embeddingKey)?t.embeddingKey:cn(e),r=e.find(e=>e.key===n);return{key:n,info:r,dims:r&&Math.max(...t.dims)<r.n_dims?t.dims:[0,1]}}function Ir({pane:e}){let t=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)?.embeddings)??[],n=W(e=>e.setWorkspace),{key:r,info:i,dims:a}=Fr(t,e);if(!t.length)return null;let o=i?Array.from({length:i.n_dims},(e,t)=>t):[],s=e=>i?.method===`pca`?`PC${e+1}`:`${i?.method?.toUpperCase()??`D`}${e+1}`;return(0,G.jsxs)(G.Fragment,{children:[(0,G.jsx)(`select`,{value:r??``,onChange:t=>n(n=>Sn(n,e.id,{embeddingKey:t.target.value,dims:[0,1]})),children:t.map(e=>(0,G.jsx)(`option`,{value:e.key,children:e.label},e.key))}),i&&i.n_dims>2&&[0,1].map(t=>(0,G.jsx)(`select`,{className:`dim`,value:a[t],onChange:r=>{let i=[...a];i[t]=+r.target.value,n(t=>Sn(t,e.id,{dims:i}))},children:o.map(e=>(0,G.jsx)(`option`,{value:e,children:s(e)},e))},t))]})}function Lr({pane:e}){let t=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)),n=W(U),r=W(e=>e.focusCell),i=W(e=>e.activeDatasetId?e.cells[e.activeDatasetId]:void 0),a=sr(),o=a.cellValues,s=W(e=>e.layers.find(t=>t.datasetId===e.activeDatasetId&&t.parentId===null)?.style.color??`#ffffff`),c=t?.embeddings??[],{key:l,dims:u}=Fr(c,e),d=gr(e),f=vr(d),p=d.kind===`group`?f:null,m=mr(d.kind===`group`?d.group:null),h=W(e=>U(e).selection),_=W(e=>e.setSelection),v=W(e=>e.saveSelection),y=W(e=>e.setError),[b,x]=(0,g.useState)(!1),[S,C]=(0,g.useState)(``),w=(0,g.useRef)(null),T=(0,g.useRef)(null),E=(0,g.useRef)(!1),[D,O]=(0,g.useState)({w:340,h:340}),k=(0,g.useRef)(null);(0,g.useEffect)(()=>{let e=k.current;if(!e)return;let t=new ResizeObserver(()=>O({w:e.clientWidth,h:e.clientHeight}));return t.observe(e),O({w:e.clientWidth,h:e.clientHeight}),()=>t.disconnect()},[]);let[A,j]=(0,g.useState)(null),[M,N]=(0,g.useState)(null),[P,F]=(0,g.useState)(null),ee=(0,g.useRef)(null);(0,g.useEffect)(()=>{if(!t||!l){j(null);return}let e=!0;return N(null),z(t.id,l,u).then(t=>e&&j(t)).catch(t=>e&&N(t.message)),()=>{e=!1}},[t?.id,l,u[0],u[1]]),(0,g.useEffect)(()=>F(null),[A,D.w,D.h]);let I=Math.max(40,D.h-24),L=(0,g.useMemo)(()=>A?Mr(A.x,A.y,jr(A.x,A.y,D.w,I,Pr)):null,[A,D.w,I]),ne=(0,g.useMemo)(()=>{if(!A)return[];let e={cellIndex:new Map((i??[]).map((e,t)=>[e.cell_id,t])),...a};return A.cell_ids.map(t=>te(re(t,n.overviewColor,s,e)))},[A,i,a,n.overviewColor,s]);(0,g.useEffect)(()=>{let t=ee.current;if(!t||!L||!A)return;let r=window.devicePixelRatio||1;t.width=Math.round(D.w*r),t.height=Math.round(I*r);let i=t.getContext(`2d`);if(!i)return;i.setTransform(r,0,0,r,0,0),i.clearRect(0,0,D.w,I);let a=A.cell_ids.length,o=Math.min(2,Math.max(1,Math.min(D.w,I)/340)),s=(a>3e3?1.6:a>800?2.4:3.4)*o,c=n.focusCell,l=p?[...Array(a).keys()].sort((e,t)=>+p.has(A.cell_ids[e])-p.has(A.cell_ids[t])):null;for(let e=0;e<a;e++){let t=l?l[e]:e,n=L[2*t],r=L[2*t+1];if(Number.isNaN(n))continue;let a=p?.has(A.cell_ids[t]);i.globalAlpha=p?a?.95:.14:c&&A.cell_ids[t]!==c?.55:.95,i.fillStyle=ne[t],i.beginPath(),i.arc(n,r,a?s*1.15:s,0,2*Math.PI),i.fill()}i.globalAlpha=1;let u=(e,t,n,r)=>{let a=L[2*e],o=L[2*e+1];Number.isNaN(a)||(i.strokeStyle=n,i.lineWidth=r,i.beginPath(),i.arc(a,o,t,0,2*Math.PI),i.stroke())};if(c){let e=A.cell_ids.indexOf(c);e>=0&&(i.fillStyle=ne[e],i.beginPath(),i.arc(L[2*e],L[2*e+1],s*2,0,2*Math.PI),i.fill(),u(e,s*2+2,`#ffffff`,2))}let d=gn(e),f=d?A.cell_ids.indexOf(d):-1;f>=0&&(u(f,s*2+5,`#5c9ded`,2.5),i.fillStyle=`#5c9ded`,i.font=`11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`,i.textAlign=`left`,i.textBaseline=`middle`,Number.isNaN(L[2*f])||i.fillText(`📌 ${d}`,L[2*f]+s*2+9,L[2*f+1])),P&&u(P.i,s+4,`rgba(255,255,255,0.8)`,1.5),p&&m&&(i.globalAlpha=1,i.fillStyle=m.color,i.font=`11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`,i.textAlign=`right`,i.textBaseline=`top`,i.fillText(`${m.name} · ${p.size} cells`,D.w-8,8))},[L,ne,A,D.w,I,n.focusCell,P,e.scope,p,m]);let ie=()=>{let e=w.current;if(!e)return;let t=window.devicePixelRatio||1;e.width=Math.round(D.w*t),e.height=Math.round(I*t),e.style.width=`${D.w}px`,e.style.height=`${I}px`;let n=e.getContext(`2d`);if(!n)return;n.setTransform(t,0,0,t,0,0),n.clearRect(0,0,D.w,I);let r=T.current;!r||r.length<2||(n.strokeStyle=`#ffffff`,n.fillStyle=`rgba(255,255,255,0.08)`,n.lineWidth=1.5,n.setLineDash([5,4]),n.beginPath(),r.forEach(([e,t],r)=>r?n.lineTo(e,t):n.moveTo(e,t)),n.closePath(),n.fill(),n.stroke())},ae=e=>{let t=e.currentTarget.getBoundingClientRect();return[e.clientX-t.left,e.clientY-t.top]},oe=e=>{if(e.button===0&&(b||e.shiftKey)&&L){e.preventDefault();try{e.currentTarget.setPointerCapture(e.pointerId)}catch{}T.current=[ae(e)],F(null)}},se=e=>{T.current&&(T.current.push(ae(e)),ie())},ce=()=>{let e=T.current;if(T.current=null,ie(),!e||!L||!A||!t)return;let n=Xe(e);if(n.length<3)return;E.current=!0;let r=Ye(L,A.cell_ids,n);r.length&&Ee(t.id,r).then(e=>_({id:e.id,cells:r})).catch(e=>y(`Cannot register the selection: ${e.message}`))},le=e=>{if(!L||T.current)return;let t=e.currentTarget.getBoundingClientRect(),n=e.clientX-t.left,r=e.clientY-t.top,i=Nr(L,n,r,8);F(i>=0?{i,x:n,y:r}:null)},ue=e=>{if(E.current){E.current=!1;return}if(!L||!A)return;let t=e.currentTarget.getBoundingClientRect(),n=Nr(L,e.clientX-t.left,e.clientY-t.top,8);n>=0&&r(A.cell_ids[n])},de=P&&A?A.cell_ids[P.i]:null,fe=de&&n.overviewColor===`field`&&o?o.get(de):void 0,pe=A?.axis_labels??[``,``];return(0,G.jsxs)(`div`,{ref:k,className:`embedding-view`,children:[!c.length&&(0,G.jsx)(`div`,{className:`muted pane-empty`,children:`This dataset has no cell embeddings (see uchrom.emb.embed_cells).`}),M&&(0,G.jsx)(`div`,{className:`error`,children:M}),(0,G.jsx)(`canvas`,{ref:ee,style:{width:D.w,height:I,cursor:b?`crosshair`:P?`pointer`:`default`,touchAction:`none`},onMouseMove:le,onMouseLeave:()=>F(null),onClick:ue,onPointerDown:oe,onPointerMove:se,onPointerUp:ce}),(0,G.jsx)(`canvas`,{ref:w,className:`emb-lasso-canvas`,"data-capture":`skip`}),c.length>0&&(0,G.jsx)(`div`,{className:`emb-tools`,"data-capture":`skip`,children:(0,G.jsx)(`button`,{className:b?`active`:``,onClick:()=>x(!b),title:`Lasso: drag around cells to select them (or shift-drag any time)`,children:`◌ lasso`})}),h&&(0,G.jsxs)(`div`,{className:`emb-selection`,"data-capture":`skip`,children:[(0,G.jsxs)(`span`,{children:[(0,G.jsx)(`b`,{children:h.cells.length}),` cells selected`]}),(0,G.jsx)(`input`,{placeholder:`name…`,value:S,onChange:e=>C(e.target.value),onKeyDown:e=>{e.key===`Enter`&&(v(S),C(``))}}),(0,G.jsx)(`button`,{onClick:()=>{v(S),C(``)},children:`Save as group`}),(0,G.jsx)(`button`,{onClick:()=>_(null),title:`Discard the selection`,children:`×`})]}),(0,G.jsxs)(`div`,{className:`embedding-axes muted small`,children:[(0,G.jsxs)(`span`,{children:[pe[0],` →`]}),(0,G.jsxs)(`span`,{children:[`↑ `,pe[1]]})]}),P&&de&&(0,G.jsxs)(`div`,{className:`embedding-tip`,style:{left:P.x+12,top:P.y+12},children:[`cell `,de,fe!==void 0&&` · ${Zn(fe)}`]})]})}var Rr=1e3;function zr(e){if(!e)return[];let t=new Map;for(let n of e.chroms??[])t.set(n.name,{name:n.name,start:n.start,end:n.end});for(let n of e.contact_maps??[])for(let e of n.chroms??[]){let n=t.get(e.name);t.set(e.name,n?{name:e.name,start:Math.min(n.start,0),end:Math.max(n.end,e.length)}:{name:e.name,start:0,end:e.length})}return[...t.values()]}function Br(e){let t=e[0];return t?{chrom:t.name,start:t.start,end:t.end}:null}function Vr(e,t){if(!t)return e;let n=t.end-t.start,r=Math.max(Math.min(Rr,n),Math.min(e.end-e.start,n));(!Number.isFinite(r)||r<=0)&&(r=n);let i=Math.round(e.start);return i<t.start&&(i=t.start),i+r>t.end&&(i=t.end-r),{chrom:e.chrom,start:i,end:Math.round(i+r)}}function Hr(e,t,n){let r=e.trim();if(!r)throw Error(`empty locus`);let i=new Map(t.map(e=>[e.name.toLowerCase(),e])),a=r.indexOf(`:`),o,s;if(a>=0)o=r.slice(0,a).trim(),s=r.slice(a+1).trim()||null;else if(i.has(r.toLowerCase()))o=r,s=null;else{if(!n)throw Error(`unknown chromosome "${r}"`);o=n.chrom,s=r}let c=i.get(o.toLowerCase());if(!c)throw Error(`unknown chromosome "${o}"`);if(!s)return{chrom:c.name,start:c.start,end:c.end};let l,u;if(/[-–]|\.\./.test(s))({start:l,end:u}=wt(s));else{let e=Ct(s);l=e-5e5,u=e+5e5}if(u<=c.start||l>=c.end)throw Error(`${c.name}:${H(l)}-${H(u)} is outside ${H(c.start)}-${H(c.end)}`);return Vr({chrom:c.name,start:Math.max(l,c.start),end:Math.min(u,c.end)},c)}function Ur(e){return`${e.chrom}:${H(e.start)}-${H(e.end)}`}function Wr(e,t,n,r){let i=e.end-e.start,a=r??(e.start+e.end)/2,o=Math.max(Rr,i*t),s=a-(i>0?(a-e.start)/i:.5)*o;return Vr({chrom:e.chrom,start:s,end:s+o},n)}function Gr(e,t,n){return Vr({chrom:e.chrom,start:e.start+t,end:e.end+t},n)}function Kr(e,t,n=5){if(!(t>e)||!Number.isFinite(e)||!Number.isFinite(t))return[];let r=(t-e)/Math.max(1,n),i=10**Math.floor(Math.log10(r)),a=[1,2,5,10].map(e=>e*i).find(e=>e>=r)??10*i,o=[];for(let n=Math.ceil(e/a)*a;n<=t+a*1e-9;n+=a)o.push(Number(n.toPrecision(12)));return o}function qr(e,t){if(!(e>0)||!(t>e))return[];let n=[];for(let r=Math.floor(Math.log10(e));r<=Math.ceil(Math.log10(t));r++){let i=10**r;i>=e*(1-1e-9)&&i<=t*(1+1e-9)&&n.push(i)}return n}function Jr(e,t=30,n){let r=[];for(let t of e)typeof t==`number`&&Number.isFinite(t)&&r.push(t);let i=Math.max(1,Math.floor(t)),a=n?n[0]:Math.min(...r),o=n?n[1]:Math.max(...r);r.length||([a,o]=[0,1]),o===a&&([a,o]=[a-.5,o+.5]);let s=(o-a)/i,c=Array.from({length:i+1},(e,t)=>a+t*s),l=Array(i).fill(0);for(let e of r)e<a||e>o||l[Math.min(i-1,Math.floor((e-a)/s))]++;return{edges:c,counts:l}}function Yr(e,t,n,r){let i=t===e?0:(r-n)/(t-e);return t=>n+(t-e)*i}function Xr(e,t,n,r){let i=Math.log10(e),a=Math.log10(t),o=a===i?0:(r-n)/(a-i);return e=>e>0?n+(Math.log10(e)-i)*o:NaN}function Zr(e){let t=1/0,n=-1/0;for(let r of e)typeof r==`number`&&Number.isFinite(r)&&(r<t&&(t=r),r>n&&(n=r));return Number.isFinite(t)?n>t?[t,n]:[t-.5,n+.5]:[0,1]}function Qr(e){let[t,n]=Zr(e);if(t<0&&n>0){let e=Math.max(-t,n);return{lo:-e,hi:e,diverging:!0}}return n<=0?{lo:t,hi:0,diverging:!1}:{lo:Math.min(0,t),hi:n,diverging:!1}}function $r(e){let t=Math.abs(e);return t===0?`0`:t>=1e6?`${+(e/1e6).toFixed(2)}M`:t>=1e3?`${+(e/1e3).toFixed(2)}k`:t>=1?`${+e.toFixed(2)}`:`${+e.toPrecision(2)}`}function ei(e,t){let n=e?t.find(t=>t.name===e.chrom):void 0;return n&&e?Vr(e,n):Br(t)}function ti(){let e=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)),t=W(e=>U(e).locus),n=W(e=>e.setLocus),r=(0,g.useMemo)(()=>zr(e),[e]),i=(0,g.useMemo)(()=>ei(t,r),[t,r]);return{locus:i,chroms:r,ext:i?r.find(e=>e.name===i.chrom):void 0,setLocus:n}}function ni({stat:e,multi:t,onStat:n,threshold:r}){let i=e===`contact`;return(0,G.jsxs)(G.Fragment,{children:[(0,G.jsxs)(`label`,{className:`insp-text small`,title:`Distance, or the fraction of traces closer than a threshold`,children:[`show`,(0,G.jsxs)(`select`,{value:i?`contact`:`distance`,onChange:e=>n(e.target.value===`contact`?`contact`:`median`),children:[(0,G.jsx)(`option`,{value:`distance`,children:`3-D distance`}),(0,G.jsx)(`option`,{value:`contact`,children:`contact frequency`})]})]}),!i&&t&&(0,G.jsxs)(`label`,{className:`insp-text small`,title:`Aggregate over the traces of the cells in scope`,children:[`aggregate`,(0,G.jsxs)(`select`,{value:e,onChange:e=>n(e.target.value),children:[(0,G.jsx)(`option`,{value:`median`,children:`median`}),(0,G.jsx)(`option`,{value:`mean`,children:`mean`})]})]}),i&&r]})}function ri({agg:e,multi:t,onAgg:n}){return t?(0,G.jsxs)(`label`,{className:`insp-text small`,title:`Aggregate the spots of the cells in scope in each bin`,children:[`aggregate`,(0,G.jsxs)(`select`,{value:e,onChange:e=>n(e.target.value),children:[(0,G.jsx)(`option`,{value:`mean`,children:`mean`}),(0,G.jsx)(`option`,{value:`median`,children:`median`}),(0,G.jsx)(`option`,{value:`max`,children:`max`})]})]}):null}function ii(){return W(e=>{let t=e.datasets.find(t=>t.id===e.activeDatasetId),n=Pn(t);return t&&n?e.cellValues[In(t.id,n.name)]:void 0})}function ai(e,t){let n=t?.get(e);return typeof n==`string`?`cell ${e} · ${n}`:`cell ${e}`}var oi=80;function si(){return W(e=>e.activeDatasetId&&e.cells[e.activeDatasetId]?.length||e.datasets.find(t=>t.id===e.activeDatasetId)?.n_cells||0)}function ci({value:e,onChange:t,view:n,title:r=`Which cells this shows`}){let i=n!==void 0,a=e??(i?{kind:`view`}:{kind:`focus`}),o=hr(),s=i?ot(a,n,o):ot(a,{kind:`all`},o),c=W(e=>e.activeDatasetId?e.cells[e.activeDatasetId]:void 0),l=si(),u=ii(),d=W(e=>U(e).selection),f=W(Un),p=W(e=>e.saveSelection),m=yr(),h=(0,g.useMemo)(()=>[...m.fields.flatMap(e=>e.refs),...m.saved],[m]),_=pr([...h,s.kind===`group`?s.group:null,d?.id??null]),v=(0,g.useMemo)(()=>new Map(_.filter(e=>!!e).map(e=>[e.ref,e])),[_]),[y,b]=(0,g.useState)(!1),[x,S]=(0,g.useState)(``),[C,w]=(0,g.useState)(null),T=x.trim().toLowerCase(),E=(0,g.useMemo)(()=>{if(!y||!c)return[];let e=[];for(let t of c){let n=u?.get(t.cell_id);if((!T||t.cell_id.toLowerCase().includes(T)||typeof n==`string`&&n.toLowerCase().includes(T))&&e.push(t.cell_id),e.length>=oi)break}return e},[y,c,T,u]),D=h.filter(e=>!T||(v.get(e)?.name??e).toLowerCase().includes(T)),O=s.kind===`group`?v.get(s.group):null,k=ht(a,s,O,l,u),A=()=>{b(!1),S(``),w(null)},j=e=>{t(e),A()},M=e=>{if(!d)return;let t=d.id;p(e?.trim()||Qe(f,`unnamed`)),j({kind:`group`,group:t})},N=e=>ct(e,a),P=(e,t,n)=>(0,G.jsxs)(`li`,{className:N(e)?`on`:``,onClick:()=>j(e),title:n,children:[(0,G.jsx)(`span`,{className:`tick`,children:N(e)?`✓`:``}),t]}),F=e=>(0,G.jsx)(`span`,{className:`swatch round`,style:{background:e?.color??`#888`}});return(0,G.jsxs)(`div`,{className:`pane-menu pane-cell scope-picker`,children:[(0,G.jsxs)(`button`,{className:a.kind===`focus`||a.kind===`view`?``:`pinned`,onClick:()=>b(!y),title:r,children:[s.kind===`group`&&F(O),k,` ▾`]}),y&&(0,G.jsxs)(`div`,{className:`pane-popup`,onMouseLeave:A,children:[(0,G.jsx)(`input`,{autoFocus:!0,placeholder:`search a cell or a group…`,value:x,onChange:e=>S(e.target.value)}),(0,G.jsxs)(`ul`,{children:[i&&P({kind:`view`},(0,G.jsxs)(G.Fragment,{children:[`Same as view `,(0,G.jsxs)(`span`,{className:`muted`,children:[`→ `,ht({kind:`all`},n,n.kind===`group`?v.get(n.group):null,l)]})]}),`Use the view's cells setting (top of the inspector)`),P({kind:`all`},(0,G.jsxs)(G.Fragment,{children:[`All cells `,(0,G.jsxs)(`span`,{className:`muted`,children:[`(`,l,`)`]})]}),`Every cell — never changes with focus, selection or lasso`),P({kind:`focus`},(0,G.jsxs)(G.Fragment,{children:[`Follow focus `,(0,G.jsxs)(`span`,{className:`muted`,children:[`→ `,ht({kind:`all`},ot({kind:`focus`},{kind:`all`},o),o.focusGroup?v.get(o.focusGroup):null,l)]})]}),`Whatever is focused: a cell, a group or the lasso selection; all cells when nothing is`),d&&!f.some(e=>e.id===d.id)&&(0,G.jsxs)(G.Fragment,{children:[(0,G.jsxs)(`li`,{className:`muted disabled head`,children:[`current lasso selection · `,d.cells.length,` cells`]}),C===null?(0,G.jsxs)(G.Fragment,{children:[(0,G.jsxs)(`li`,{onClick:()=>M(null),title:`Keep exactly these cells (saved as an unnamed group) — a new lasso won't change this`,children:[(0,G.jsx)(`span`,{className:`tick`,children:`❄`}),`freeze these `,d.cells.length,` cells`]}),(0,G.jsxs)(`li`,{onClick:()=>w(``),title:`Save the selection as a named group and use it`,children:[(0,G.jsx)(`span`,{className:`tick`,children:`＋`}),`save as group…`]})]}):(0,G.jsxs)(`li`,{className:`naming`,children:[(0,G.jsx)(`input`,{autoFocus:!0,placeholder:`group name…`,value:C,onChange:e=>w(e.target.value),onKeyDown:e=>e.key===`Enter`&&M(C)}),(0,G.jsx)(`button`,{onClick:()=>M(C),children:`Save`})]})]}),D.length>0&&(0,G.jsx)(`li`,{className:`muted disabled head`,children:`groups`}),D.map(e=>(0,G.jsxs)(`li`,{className:N({kind:`group`,group:e})?`on`:``,onClick:()=>j({kind:`group`,group:e}),children:[(0,G.jsx)(`span`,{className:`tick`,children:N({kind:`group`,group:e})?`✓`:``}),F(v.get(e)),v.get(e)?.name??e,(0,G.jsxs)(`span`,{className:`muted`,children:[` · `,v.get(e)?.cells?`${v.get(e).cells.length} cells`:`…`]})]},e)),E.length>0&&(0,G.jsx)(`li`,{className:`muted disabled head`,children:`cells`}),E.map(e=>(0,G.jsxs)(`li`,{className:N({kind:`cell`,cell:e})?`on`:``,onClick:()=>j({kind:`cell`,cell:e}),children:[(0,G.jsx)(`span`,{className:`tick`,children:N({kind:`cell`,cell:e})?`✓`:``}),e,typeof u?.get(e)==`string`&&(0,G.jsxs)(`span`,{className:`muted`,children:[` · `,u.get(e)]})]},e)),E.length>=oi&&(0,G.jsx)(`li`,{className:`muted disabled`,children:`… type to narrow down`})]})]})]})}var li={axis:`rgba(216,218,223,0.55)`,grid:`rgba(216,218,223,0.08)`,text:`#b9bdc4`,muted:`#8f949c`,accent:`#5c9ded`,font:`11px -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif`};function ui(e,t,n,r){e.save(),e.font=li.font,e.lineWidth=1,e.strokeStyle=li.grid;for(let n of r.ticks){let i=Math.round(r.pos(n))+.5;i<t.y-1||i>t.y+t.h+1||(e.beginPath(),e.moveTo(t.x,i),e.lineTo(t.x+t.w,i),e.stroke())}e.strokeStyle=li.axis,e.beginPath(),e.moveTo(t.x+.5,t.y),e.lineTo(t.x+.5,t.y+t.h+.5),e.lineTo(t.x+t.w,t.y+t.h+.5),e.stroke(),e.fillStyle=li.text,e.textAlign=`center`,e.textBaseline=`top`;for(let r of n.ticks){let i=Math.round(n.pos(r))+.5;i<t.x-1||i>t.x+t.w+1||(e.beginPath(),e.moveTo(i,t.y+t.h),e.lineTo(i,t.y+t.h+4),e.stroke(),e.fillText(n.fmt(r),i,t.y+t.h+6))}e.textAlign=`right`,e.textBaseline=`middle`;for(let n of r.ticks){let i=Math.round(r.pos(n))+.5;i<t.y-1||i>t.y+t.h+1||(e.beginPath(),e.moveTo(t.x-4,i),e.lineTo(t.x,i),e.stroke(),e.fillText(r.fmt(n),t.x-6,i))}e.fillStyle=li.muted,n.label&&(e.textAlign=`center`,e.textBaseline=`bottom`,e.fillText(n.label,t.x+t.w/2,t.y+t.h+34)),r.label&&(e.translate(t.x-44,t.y+t.h/2),e.rotate(-Math.PI/2),e.textAlign=`center`,e.textBaseline=`top`,e.fillText(r.label,0,0)),e.restore()}function di(e,t,n,r,i,a){let o=Math.max(2,Math.floor(t.w));for(let r=0;r<o;r++)e.fillStyle=n(r/(o-1)),e.fillRect(t.x+r*t.w/o,t.y,t.w/o+1,t.h);e.save(),e.font=li.font,e.fillStyle=li.text,e.textBaseline=`top`,e.textAlign=`left`,e.fillText(r,t.x,t.y+t.h+3),e.textAlign=`right`,e.fillText(i,t.x+t.w,t.y+t.h+3),a&&(e.textAlign=`left`,e.textBaseline=`bottom`,e.fillStyle=li.muted,e.fillText(a,t.x,t.y-3)),e.restore()}var fi=(e,t=1)=>t>=1?`rgb(${Math.round(e[0]*255)},${Math.round(e[1]*255)},${Math.round(e[2]*255)})`:`rgba(${Math.round(e[0]*255)},${Math.round(e[1]*255)},${Math.round(e[2]*255)},${t})`,pi=26,mi=`#e8784f`,hi=`#4f8fe8`,gi=`#6aa4ef`,_i=`rgba(255,255,255,0.16)`,vi={median:`median distance`,mean:`mean distance`,contact:`contact frequency`},yi=32,bi=new Map,xi=new Map;function Si(e,t){let n=bi.get(e);if(n)return bi.delete(e),bi.set(e,n),Promise.resolve(n);let r=xi.get(e);return r||(r=t().then(t=>{for(bi.set(e,t);bi.size>yi;)bi.delete(bi.keys().next().value);return t}).finally(()=>xi.delete(e)),xi.set(e,r)),r}function Ci(e){let t=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)),n=W(e=>e.setWorkspace),r=t?e.genomeRows?.[t.name]:void 0;return{ds:t,rows:(0,g.useMemo)(()=>r??Gt(t,e.tracks),[r,t,e.tracks]),setRows:(0,g.useCallback)(r=>{t&&n(n=>{let i=n.panes.find(t=>t.id===e.id);if(!i)return n;let a=i.genomeRows?.[t.name]??Gt(t,i.tracks);return Sn(n,e.id,{genomeRows:{...i.genomeRows??{},[t.name]:r(a)}})})},[t,e.id,n]),resetRows:(0,g.useCallback)(()=>{t&&n(n=>{let r=n.panes.find(t=>t.id===e.id);if(!r?.genomeRows?.[t.name])return n;let{[t.name]:i,...a}=r.genomeRows;return Sn(n,e.id,{genomeRows:a})})},[t,e.id,n]),customised:!!r}}function wi(e,t,n){if(e===`matrix`){let r=new Set(t.map(e=>e.source)),i=[...(n.contact_maps??[]).map(e=>e.key),...Nn(n)?[`distance`]:[]];return{kind:e,source:i.find(e=>!r.has(e))??i[0]??null}}if(e===`track`){let r=new Set(t.map(e=>e.track)),i=(n.tracks??[]).map(e=>e.name);return{kind:e,track:i.find(e=>!r.has(e))??i[0]??null}}let r=new Set(t.map(e=>e.key)),i=(n.intervals??[]).map(e=>e.key);return{kind:e,key:i.find(e=>!r.has(e))??i[0]??null}}var Ti={matrix:`Matrix`,track:`Track`,intervals:`Intervals`};function Ei(e,t){if(e.kind===`matrix`){if(e.source===`distance`)return`3-D distance · ${e.stat??`median`}`;let n=(t.contact_maps??[]).find(t=>t.key===e.source);return n?n.label||n.key:e.source??`—`}return(e.kind===`track`?e.track:e.key)??`—`}function Di({pane:e}){let{ds:t,rows:n,setRows:r,resetRows:i,customised:a}=Ci(e),o=gr(e);if(!t)return null;let s={matrix:(t.contact_maps?.length??0)>0||Nn(t),track:(t.tracks?.length??0)>0,intervals:(t.intervals?.length??0)>0},c=e=>(t,n)=>r(r=>Wt(r,e,t,n));return(0,G.jsxs)(`section`,{className:`insp-genome`,children:[(0,G.jsxs)(`h2`,{children:[`Rows `,(0,G.jsx)(`span`,{className:`muted`,children:n.length}),a&&(0,G.jsx)(`button`,{className:`link`,onClick:i,title:`Back to the default rows for this dataset`,children:`reset`})]}),(0,G.jsx)(`div`,{className:`seg insp-add`,children:[`matrix`,`track`,`intervals`].map(e=>(0,G.jsxs)(`button`,{disabled:!s[e],onClick:()=>r(n=>Rt(n,wi(e,n,t))),title:s[e]?`Add a ${Ti[e].toLowerCase()} row`:`Not available in this dataset`,children:[`+ `,Ti[e]]},e))}),!n.length&&(0,G.jsx)(`p`,{className:`muted small`,children:`No rows — add one above.`}),(0,G.jsx)(`ol`,{className:`row-list`,children:n.map((i,a)=>(0,G.jsxs)(`li`,{className:`row-card ${i.kind}`,children:[(0,G.jsxs)(`div`,{className:`row-card-head`,children:[(0,G.jsx)(`span`,{className:`row-kind`,children:Ti[i.kind]}),(0,G.jsx)(`span`,{className:`row-name`,title:Ei(i,t),children:Ei(i,t)}),(0,G.jsx)(`button`,{onClick:()=>r(e=>Bt(e,i.id,-1)),disabled:a===0,title:`Move up`,children:`↑`}),(0,G.jsx)(`button`,{onClick:()=>r(e=>Bt(e,i.id,1)),disabled:a===n.length-1,title:`Move down`,children:`↓`}),(0,G.jsx)(`button`,{onClick:()=>r(e=>zt(e,i.id)),title:`Remove this row`,children:`×`})]}),(0,G.jsx)(ki,{row:i,ds:t,set:c(i.id),view:o,defaultAgg:e.agg??`mean`,setScope:e=>r(t=>Jt(t,i.id,e))})]},i.id))}),(0,G.jsx)(`div`,{className:`muted small`,children:`Drag a row’s bottom edge in the view to resize it; wheel zooms, drag pans.`})]})}function Oi(e,t){return e.kind===`track`?!0:e.kind===`matrix`?e.source===`distance`?Nn(t):!!(t.contact_maps??[]).find(t=>t.key===e.source)?.per_cell:!1}function ki({row:e,ds:t,set:n,view:r,defaultAgg:i,setScope:a}){let o=lt(_r(e.scope,r)),s=e.kind===`matrix`&&e.source!==`distance`&&!!(t.contact_maps??[]).find(t=>t.key===e.source)?.per_cell;return(0,G.jsxs)(`div`,{className:`row-card-body`,children:[e.kind===`matrix`&&(0,G.jsx)(Pi,{row:e,ds:t,set:n,multi:o}),e.kind===`track`&&(0,G.jsx)(`select`,{value:e.track??``,onChange:e=>n(`track`,e.target.value),title:`Track`,children:(t.tracks??[]).map(e=>(0,G.jsx)(`option`,{value:e.name,children:e.name},e.name))}),Oi(e,t)&&(0,G.jsxs)(`label`,{className:`insp-text small scope-line`,title:`Which cells this row shows`,children:[`cells`,(0,G.jsx)(ci,{value:e.scope,onChange:a,view:r})]}),e.kind===`matrix`&&!Oi(e,t)&&e.source!==`distance`&&(0,G.jsx)(`div`,{className:`muted small`,children:`bulk map: all cells in the file`}),s&&o&&(0,G.jsx)(`div`,{className:`muted small`,children:`several cells: their maps are summed (pseudo-bulk)`}),e.kind===`track`&&(0,G.jsx)(ri,{agg:e.agg??i,multi:o,onAgg:e=>n(`agg`,e)}),e.kind===`intervals`&&(0,G.jsx)(`select`,{value:e.key??``,onChange:e=>n(`key`,e.target.value),title:`Interval table`,children:(t.intervals??[]).map(e=>(0,G.jsx)(`option`,{value:e.key,children:e.key},e.key))}),(0,G.jsx)(Ai,{label:`height`,value:e.height?String(e.height):``,placeholder:e.kind===`matrix`?`auto`:String(Ft[e.kind]),onCommit:e=>n(`height`,e),title:`Row height in px (empty = default)`})]})}function Ai({label:e,value:t,placeholder:n,title:r,onCommit:i}){let[a,o]=(0,g.useState)(t);return(0,g.useEffect)(()=>o(t),[t]),(0,G.jsxs)(`label`,{className:`insp-text small`,title:r,children:[e,(0,G.jsx)(`input`,{className:`num`,value:a,placeholder:n,onChange:e=>o(e.target.value),onBlur:()=>{i(a),o(t)},onKeyDown:e=>e.key===`Enter`&&e.target.blur()})]})}function ji({pane:e}){let{ds:t,rows:n,setRows:r}=Ci(e),i=gr(e),a=hr(),o=si(),s=(0,g.useMemo)(()=>n.map(e=>ot(e.scope,i,a)),[n,i,a]),c=pr(s.map(e=>e.kind===`group`?e.group:null)),l=(0,g.useMemo)(()=>new Map(c.filter(e=>!!e).map(e=>[e.ref,e])),[c]),{locus:u,ext:d,setLocus:f}=ti(),p=(0,g.useRef)(null),m=(0,g.useRef)(null),{w:h,h:_}=br(m),v=(0,g.useMemo)(()=>It(n,_,h),[n,_,h]),[y,b]=(0,g.useState)(null),x=(0,g.useRef)(new Map),S=(0,g.useCallback)((e,t)=>{t?x.current.set(e,t):x.current.delete(e)},[]),C=(0,g.useMemo)(()=>new Set((t?.tracks??[]).map(e=>e.name)),[t]),w=(0,g.useMemo)(()=>{let t=new Map;return n.forEach((n,r)=>{if(n.kind!==`track`||!n.track||!C.has(n.track))return;let i=s[r],a=n.agg??e.agg??`mean`,o=`${dt(i)}|${a}`,c=t.get(o)??{scope:i,agg:a,names:[]};c.names.includes(n.track)||c.names.push(n.track),t.set(o,c)}),t},[n,C,s,e.agg]),T=[...w].map(([e,t])=>`${e}=${t.names.join(`,`)}`).join(`|`),[E,D]=(0,g.useState)({}),[O,k]=(0,g.useState)(null);(0,g.useEffect)(()=>{if(!t||!u||!w.size)return;let e=!0,n=setTimeout(()=>{for(let[n,r]of w){let i=ut(r.scope);Me(t.id,r.names,u,{cellId:i.cellId,group:i.group,agg:r.agg}).then(t=>e&&(D(e=>({...e,[n]:t})),k(null))).catch(t=>e&&k(t.message))}},180);return()=>{e=!1,clearTimeout(n)}},[t?.id,T,u?.chrom,u?.start,u?.end]);let A=[...new Set(n.filter(e=>e.kind===`intervals`&&e.key).map(e=>e.key))],j=A.join(`,`),[M,N]=(0,g.useState)({});(0,g.useEffect)(()=>{if(!t||!u||!A.length)return;let e=!0,n=setTimeout(()=>{for(let n of A)Ne(t.id,n,u).then(t=>e&&N(e=>({...e,[n]:t}))).catch(()=>void 0)},180);return()=>{e=!1,clearTimeout(n)}},[t?.id,j,u?.chrom,u?.start,u?.end]);let P=(0,g.useMemo)(()=>{if(!u)return[];let e=new Set;for(let t of A){let n=M[t];if(!n)continue;let r=e=>n.columns.indexOf(e),[i,a,o,s]=[r(`start`),r(`end`),r(`chrom`),r(`start2`)];for(let t of n.rows)if(!(o>=0&&t[o]!==u.chrom)&&!(s>=0&&t[s]!==null))for(let n of[Number(t[i]),Number(t[a])])n>u.start&&n<u.end&&e.add(n)}return[...e]},[M,j,u]),F=(0,g.useRef)(null);F.current=u;let ee=(0,g.useRef)(d);ee.current=d,(0,g.useEffect)(()=>{let e=p.current;if(!e)return;let t=e=>{let t=F.current,n=m.current;if(!t||!n||e.target.closest(`.gv-tools`))return;e.preventDefault();let r=n.getBoundingClientRect(),i=t.start+(e.clientX-r.left)/n.clientWidth*(t.end-t.start);f(Wr(t,Math.exp(e.deltaY*.0015),ee.current,i))};return e.addEventListener(`wheel`,t,{passive:!1}),()=>e.removeEventListener(`wheel`,t)},[f]);let te=e=>{if(!u||e.button!==0||e.target.closest(`.gv-tools, .gv-resize, select, input, button`))return;let t={x:e.clientX,locus:u},n=m.current?.clientWidth||1,r=e=>{f(Gr(t.locus,-(e.clientX-t.x)/n*(t.locus.end-t.locus.start),ee.current)),b(null)},i=()=>{window.removeEventListener(`pointermove`,r),window.removeEventListener(`pointerup`,i)};window.addEventListener(`pointermove`,r),window.addEventListener(`pointerup`,i)},I=e=>{let t=p.current,n=m.current;if(!t||!n||e.buttons)return;let r=t.getBoundingClientRect(),i=e.clientX-r.left;if(i<0||i>=n.clientWidth||e.target.closest(`.gv-tools`))return b(null);let a=null,o=e.target.closest(`[data-row]`),s=o?.querySelector(`canvas`);if(o&&s){let t=s.getBoundingClientRect();a=x.current.get(o.dataset.row)?.(e.clientX-t.left,e.clientY-t.top)??null}else u&&(a=`${u.chrom}:${H(Math.round(u.start+i/n.clientWidth*(u.end-u.start)))}`);b({x:i,y:e.clientY-r.top,text:a})},L=null;t?u?n.length||(L=`No rows — add one with “+ Row”.`):L=`No chromosomes to show.`:L=`No dataset.`;let ne=p.current?.clientWidth??h;return(0,G.jsxs)(`div`,{ref:p,className:`genome-view gv`,onPointerDown:te,onMouseMove:I,onMouseLeave:()=>b(null),children:[L&&(0,G.jsx)(`div`,{className:`muted pane-empty`,children:L}),O&&(0,G.jsx)(`div`,{className:`error pane-error`,children:O}),u&&h>0&&(0,G.jsx)(Mi,{width:h,locus:u}),(0,G.jsx)(`div`,{ref:m,className:`gv-rows`,children:t&&u&&h>0&&n.map((n,i)=>(0,G.jsxs)(Ni,{row:n,height:v[i],setRows:r,children:[n.kind===`matrix`&&(0,G.jsx)(Li,{row:n,height:v[i],ds:t,width:h,locus:u,scope:s[i],group:s[i].kind===`group`?l.get(s[i].group)??null:null,nAll:o,guides:P,register:S}),n.kind===`track`&&(0,G.jsx)(Ri,{row:n,height:v[i],width:h,locus:u,data:E[`${dt(s[i])}|${n.agg??e.agg??`mean`}`]??null,label:`${mt(s[i],s[i].kind===`group`?l.get(s[i].group):null,o)}${lt(s[i])?` · ${n.agg??e.agg??`mean`}`:``}`,color:s[i].kind===`group`?l.get(s[i].group)?.color??null:null,register:S}),n.kind===`intervals`&&(0,G.jsx)(zi,{row:n,height:v[i],width:h,locus:u,table:n.key?M[n.key]:void 0,register:S})]},n.id))}),y&&(0,G.jsx)(`div`,{className:`gv-cross`,style:{left:y.x}}),y?.text&&(0,G.jsx)(`div`,{className:`embedding-tip`,style:y.x>ne/2?{right:ne-y.x+12,top:y.y+14}:{left:y.x+12,top:y.y+14},children:y.text})]})}function Mi({width:e,locus:t}){let n=(0,g.useRef)(null);return(0,g.useEffect)(()=>{let r=n.current;if(!r)return;let i=xr(r,e,pi);if(!i)return;let a=t.end-t.start,o=n=>(n-t.start)/a*e;i.font=li.font,i.strokeStyle=li.axis,i.fillStyle=li.text,i.textBaseline=`top`;for(let n of Kr(t.start,t.end,Math.max(2,Math.floor(e/110)))){let t=Math.round(o(n))+.5;i.beginPath(),i.moveTo(t,19),i.lineTo(t,pi),i.stroke();let r=H(n),a=i.measureText(r).width/2;i.textAlign=`center`,i.fillText(r,Math.max(a+2,Math.min(t,e-a-2)),4)}i.beginPath(),i.moveTo(0,25.5),i.lineTo(e,25.5),i.stroke()},[e,t]),(0,G.jsx)(`canvas`,{ref:n,className:`gv-axis`,style:{width:e,height:pi}})}function Ni({row:e,height:t,setRows:n,children:r}){return(0,G.jsxs)(`div`,{className:`gv-row ${e.kind}`,"data-row":e.id,style:{height:t},children:[r,(0,G.jsx)(`div`,{className:`gv-resize`,onPointerDown:r=>{r.preventDefault(),r.stopPropagation();let i=r.clientY,a=t,o=t=>n(n=>Ht(n,e.id,a+t.clientY-i)),s=()=>{window.removeEventListener(`pointermove`,o),window.removeEventListener(`pointerup`,s),document.body.classList.remove(`resizing-rows`)};document.body.classList.add(`resizing-rows`),window.addEventListener(`pointermove`,o),window.addEventListener(`pointerup`,s)},title:`Drag to change the row height`})]})}function Pi({row:e,ds:t,set:n,multi:r}){let i=t.contact_maps??[],a=i.find(t=>t.key===e.source);return(0,G.jsxs)(G.Fragment,{children:[(0,G.jsxs)(`select`,{value:e.source??``,onChange:e=>n(`source`,e.target.value),title:`Matrix source`,children:[i.map(e=>(0,G.jsxs)(`option`,{value:e.key,children:[e.label||e.key,` (`,e.kind,`)`]},e.key)),Nn(t)&&(0,G.jsx)(`option`,{value:`distance`,children:`3-D distance`})]}),a&&a.resolutions.length>1&&(0,G.jsxs)(`select`,{value:e.resolution??``,onChange:e=>n(`resolution`,e.target.value),title:`Resolution`,children:[(0,G.jsx)(`option`,{value:``,children:`auto resolution`}),a.resolutions.map(e=>(0,G.jsx)(`option`,{value:e,children:H(e)},e))]}),a&&(0,G.jsxs)(`label`,{className:`check small`,title:`ICE-balanced values (if the cooler has weights)`,children:[(0,G.jsx)(`input`,{type:`checkbox`,checked:e.balance??!1,onChange:e=>n(`balance`,e.target.checked)}),` balanced`]}),e.source===`distance`&&(0,G.jsx)(ni,{stat:e.stat??`median`,multi:r,onStat:e=>n(`stat`,e),threshold:(0,G.jsx)(Ai,{label:`threshold`,value:e.threshold?String(e.threshold):``,placeholder:`default`,title:`Contact distance threshold (${t.xyz_unit??`dataset unit`}); empty = server default`,onCommit:e=>n(`threshold`,e)})}),(0,G.jsx)(Ai,{label:`max dist`,value:e.maxDist?H(e.maxDist):``,placeholder:`45°`,title:`Deepest genomic separation shown over the row height (e.g. 5M); empty = true 45°`,onCommit:e=>n(`maxDist`,e)}),(0,G.jsxs)(`label`,{className:`check small`,title:`Diagonal at the top of the row (triangle pointing down)`,children:[(0,G.jsx)(`input`,{type:`checkbox`,checked:!!e.flip,onChange:e=>n(`flip`,e.target.checked)}),` flip`]})]})}function Fi(e,t){return{ref:(0,g.useRef)(null),style:{width:e,height:t}}}function Ii(e,t,n){let r=(0,g.useRef)(n);r.current=n,(0,g.useEffect)(()=>(e(t,(e,t)=>r.current(e,t)),()=>e(t,null)),[e,t])}function Li({row:e,height:t,ds:n,width:r,locus:i,scope:a,group:o,nAll:s,guides:c,register:l}){let{ref:u,style:d}=Fi(r,t),f=(n.contact_maps??[]).find(t=>t.key===e.source),p=e.source===`distance`,m=p?Nn(n):!!f,h=!!f?.per_cell,_=h||p,v=_&&a.kind===`cell`?a.cell:null,y=_&&a.kind===`group`?a.group:h&&a.kind===`all`?`all`:null,b=e.stat??`median`,[x,S]=(0,g.useState)(null),[C,w]=(0,g.useState)(null),[T,E]=(0,g.useState)(!1);(0,g.useEffect)(()=>{if(!m){S(null),w(null);return}let t=[n.id,e.source,i.chrom,i.start,i.end,e.resolution??``,+!!e.balance,v??``,y??``,b,e.threshold??``].join(`|`),r=!0,a=()=>p?Fe(n.id,i,{cellId:v,group:y,stat:b,threshold:e.threshold??null}):Pe(n.id,e.source,i,{resolution:e.resolution??null,balance:e.balance??!1,cell:v,group:y}),o=setTimeout(()=>{E(!0),Si(t,a).then(e=>r&&(S(e),w(null))).catch(e=>r&&w(e.message)).finally(()=>r&&E(!1))},bi.has(t)?0:200);return()=>{r=!1,clearTimeout(o)}},[n.id,e.source,i.chrom,i.start,i.end,e.resolution,e.balance,v,y,b,e.threshold,m,!1]);let D=x&&x.header.chrom===i.chrom&&m?x:null,O=D?oe(D.header.value):`contacts`,k=(0,g.useMemo)(()=>D?ce(D.data,O):[0,1],[D,O]),A=(0,g.useMemo)(()=>D?pe(D,O,k):null,[D,O,k]),j=Yt(e.maxDist,(i.end-i.start)/r,t),M={start:i.start,bpPerPx:(i.end-i.start)/r,height:t,k:j,flip:!!e.flip,maxDist:e.maxDist??null},N=p?`3-D distance · ${vi[b]}`:f?f.label||f.key:`unknown source “${e.source}”`,P=D?.header.n_cells?`${D.header.n_cells} cells`:null,F=[_?mt(a,o,s):`bulk map`,_&&a.kind!==`cell`&&P&&D?.header.n_cells!==(a.kind===`all`?s:o?.cells?.length)?`${P} with data`:null,D?.header.resolution?`${H(D.header.resolution)} bins`:null,D?.header.n_traces?`${D.header.n_traces} traces`:null,h&&y&&D?.header.n_contacts?`${$r(D.header.n_contacts)} contacts (pseudo-bulk)`:null].filter(Boolean).join(` · `);return(0,g.useEffect)(()=>{let n=u.current;if(!n)return;let s=xr(n,r,t);if(!s)return;let l=n.width/r;if(D&&A){let e={...M,bpPerPx:M.bpPerPx/l,height:n.height},t=$t(n.width,n.height,e,D.header.bin_starts,D.header.bin_ends,A);s.putImageData(new ImageData(t,n.width,n.height),0,0)}if(c.length){s.strokeStyle=_i,s.lineWidth=1,s.setLineDash([3,3]);for(let e of c){let n=Math.round((e-i.start)/(i.end-i.start)*r)+.5;s.beginPath(),s.moveTo(n,0),s.lineTo(n,t),s.stroke()}s.setLineDash([])}let d=e.flip?t-44:4;if(s.font=li.font,s.textAlign=`left`,s.textBaseline=`top`,s.fillStyle=li.text,s.fillText(N,6,d),F){let e=6;a.kind===`group`&&o&&_&&(s.fillStyle=o.color,s.beginPath(),s.arc(e+4,d+20,4,0,2*Math.PI),s.fill(),e+=12),s.fillStyle=li.muted,s.fillText(F,e,d+14)}if(D&&t>=70){let n=O===`contacts`?`0`:$r(k[0]),i=O===`contacts`?`≥${$r(Math.expm1(k[1]))}`:$r(k[1]);s.save(),s.textAlign=`right`,di(s,{x:r-70-8,y:e.flip?t-22:8,w:70,h:6},e=>fi(fe(O===`contacts`?Math.expm1(e*k[1]):k[0]+e*(k[1]-k[0]),O,k)),n,i),s.restore()}let f=m?C:N;f&&(s.fillStyle=C?`#e07a7a`:li.muted,s.textAlign=`center`,s.textBaseline=`middle`,s.fillText(f,r/2,t/2)),T&&!D&&(s.fillStyle=li.muted,s.textAlign=`center`,s.textBaseline=`middle`,s.fillText(`loading…`,r/2,t/2))},[D,A,r,t,i,j,e.flip,e.maxDist,c,N,F,C,!1,m,T,o,y]),Ii(l,e.id,(e,t)=>{if(!D)return null;let n=D.header,r=Zt(e,t,M,n.bin_starts,n.bin_ends);if(!r)return null;let[i,a]=r,o=D.data[i*n.n_cols+a],s=O===`distance`&&n.unit?` ${n.unit}`:``;return`${N} · bins ${i}, ${a} · ${n.chrom}:${H(n.bin_starts[i])} × ${H(n.bin_starts[a])} · ${Number.isFinite(o)?$r(o):`—`}${s}`}),(0,G.jsxs)(G.Fragment,{children:[(0,G.jsx)(`canvas`,{ref:u,style:d}),T&&D&&(0,G.jsx)(`div`,{className:`gv-row-loading muted small`,children:`loading…`})]})}function Ri({row:e,height:t,width:n,locus:r,data:i,label:a,color:o,register:s}){let{ref:c,style:l}=Fi(n,t),u=e.track??``,d=i?.chrom===r.chrom?i.values[u]:void 0;return(0,g.useEffect)(()=>{let e=c.current;if(!e)return;let s=xr(e,n,t);if(!s)return;let l=e=>(e-r.start)/(r.end-r.start)*n;if(s.fillStyle=`rgba(255,255,255,0.03)`,s.fillRect(0,0,n,t-1),s.font=li.font,d&&i){let{lo:e,hi:r,diverging:a}=Qr(d),o=t-3,c=n=>o-(n-e)/(r-e||1)*Math.max(4,t-16),u=c(0);for(let e=0;e<i.bin_starts.length;e++){let t=d[e];if(typeof t!=`number`||!Number.isFinite(t))continue;let n=l(i.bin_starts[e]),r=Math.max(1,l(i.bin_ends[e])-n),o=c(t);s.fillStyle=a?t>=0?mi:hi:gi,s.fillRect(n,Math.min(o,u),r,Math.max(1,Math.abs(u-o)))}a&&(s.strokeStyle=`rgba(255,255,255,0.18)`,s.beginPath(),s.moveTo(0,Math.round(u)+.5),s.lineTo(n,Math.round(u)+.5),s.stroke()),s.fillStyle=li.muted,s.textAlign=`right`,s.textBaseline=`top`,s.fillText(`${$r(e)} … ${$r(r)}`,n-6,2)}s.fillStyle=li.text,s.textAlign=`left`,s.textBaseline=`top`,s.fillText(u||`(no track)`,6,2);let f=6+s.measureText(u||`(no track)`).width+10;o&&(s.fillStyle=o,s.beginPath(),s.arc(f+4,8,4,0,2*Math.PI),s.fill(),f+=12),s.fillStyle=li.muted,s.fillText(a,f,2)},[d,i,n,t,r,u,a,o]),Ii(s,e.id,e=>{if(!d||!i)return null;let t=r.start+e/n*(r.end-r.start),a=Pt(i.bin_starts,i.bin_ends,t,(r.end-r.start)/n*2);if(a<0)return null;let o=d[a];return`${u} · ${i.chrom}:${H(i.bin_starts[a])}-${H(i.bin_ends[a])} · ${o==null?`—`:$r(o)} (${i.n_spots[a]} spots)`}),(0,G.jsx)(`canvas`,{ref:c,style:l})}function zi({row:e,height:t,width:n,locus:r,table:i,register:a}){let{ref:o,style:s}=Fi(n,t),c=(0,g.useMemo)(()=>{if(!i)return[];let e=e=>i.columns.indexOf(e),[t,n,a,o,s]=[e(`start`),e(`end`),e(`chrom`),e(`start2`),e(`end2`)];return i.rows.filter(e=>a<0||e[a]===r.chrom).map(e=>({s:Number(e[t]),e:Number(e[n]),s2:o>=0&&e[o]!==null?Number(e[o]):null,e2:s>=0&&e[s]!==null?Number(e[s]):null}))},[i,r.chrom]);return(0,g.useEffect)(()=>{let i=o.current;if(!i)return;let a=xr(i,n,t);if(!a)return;let s=e=>(e-r.start)/(r.end-r.start)*n;for(let e of c)if(e.s2!==null&&e.e2!==null){let n=s((e.s+e.e)/2),r=s((e.s2+e.e2)/2);a.strokeStyle=`#d08bf0`,a.beginPath(),a.moveTo(n,t-2),a.quadraticCurveTo((n+r)/2,-t*.6,r,t-2),a.stroke()}else{let n=s(e.s),r=Math.max(1,s(e.e)-n);a.fillStyle=`rgba(92,157,237,0.35)`,a.strokeStyle=`rgba(92,157,237,0.9)`,a.fillRect(n,3,r,t-6),a.strokeRect(n+.5,3.5,r-1,t-7)}a.font=li.font,a.fillStyle=li.muted,a.textAlign=`left`,a.textBaseline=`top`,a.fillText(e.key??``,6,Math.max(0,t/2-7))},[c,n,t,r,e.key]),Ii(a,e.id,t=>{let i=r.start+t/n*(r.end-r.start),a=c.find(e=>e.s2===null&&i>=e.s&&i<e.e);return a?`${e.key} · ${r.chrom}:${H(a.s)}-${H(a.e)}`:null}),(0,G.jsx)(`canvas`,{ref:o,style:s})}function Bi(){let e=W(e=>e.activeDatasetId),t=W(e=>e.layers),n=W(e=>e.selectedLayerId),r=W(e=>e.selectLayer),i=W(e=>e.setVisible),a=W(e=>e.renameLayer),o=W(e=>e.removeLayer),[s,c]=(0,g.useState)(null),l=yt(t.filter(t=>t.datasetId===e));return(0,G.jsxs)(`section`,{className:`panel`,children:[(0,G.jsx)(`h2`,{children:`Layers`}),!l.length&&(0,G.jsx)(`p`,{className:`muted`,children:`Open a dataset to start.`}),(0,G.jsx)(`ul`,{className:`layer-list`,children:l.map(({layer:e,depth:t})=>(0,G.jsxs)(`li`,{className:e.id===n?`selected`:``,style:{paddingLeft:6+t*14},onClick:()=>r(e.id),children:[(0,G.jsx)(`button`,{className:`eye ${e.visible?`on`:``}`,title:e.visible?`Hide`:`Show`,onClick:t=>{t.stopPropagation(),i(e.id,!e.visible)},children:e.visible?`●`:`○`}),s===e.id?(0,G.jsx)(`input`,{className:`rename`,autoFocus:!0,defaultValue:e.name,onClick:e=>e.stopPropagation(),onBlur:t=>{a(e.id,t.target.value),c(null)},onKeyDown:e=>{e.key===`Enter`&&e.target.blur(),e.key===`Escape`&&c(null)}}):(0,G.jsx)(`span`,{className:`name`,title:`Double-click to rename`,onDoubleClick:()=>c(e.id),children:e.name}),(0,G.jsx)(`span`,{className:`layer-state`,children:e.loading?`…`:e.error?`!`:e.geometry?e.geometry.header.n_points.toLocaleString(`en-US`):``}),(0,G.jsx)(`button`,{className:`del`,title:e.parentId?`Delete layer and its children`:`Delete layer`,onClick:t=>{t.stopPropagation(),o(e.id)},children:`×`})]},e.id))})]})}var Vi={left:64,top:10,right:12,bottom:76};function Hi(e,t,n){return e.source===`distance`&&n?`distance`:e.source&&t.some(t=>t.key===e.source)?e.source:t[0]?.key??(n?`distance`:null)}function Ui({pane:e}){let t=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)),n=W(e=>e.setWorkspace),r=t?.contact_maps??[],i=t?.has_coords!==!1&&(t?.n_spots??0)>0,a=Hi(e,r,i),o=r.find(e=>e.key===a),s=t=>n(n=>Sn(n,e.id,t)),c=gr(e);return a?(0,G.jsxs)(G.Fragment,{children:[(0,G.jsxs)(`select`,{value:a,onChange:e=>s({source:e.target.value,resolution:null}),title:`Matrix source`,children:[r.map(e=>(0,G.jsxs)(`option`,{value:e.key,children:[e.label||e.key,` (`,e.kind,`)`]},e.key)),i&&(0,G.jsx)(`option`,{value:`distance`,children:`3-D distance`})]}),o&&o.resolutions.length>1&&(0,G.jsxs)(`select`,{value:e.resolution??``,onChange:e=>s({resolution:e.target.value?+e.target.value:null}),title:`Resolution`,children:[(0,G.jsx)(`option`,{value:``,children:`auto`}),o.resolutions.map(e=>(0,G.jsx)(`option`,{value:e,children:H(e)},e))]}),o&&(0,G.jsxs)(`label`,{className:`check small`,title:`ICE-balanced values (if the cooler has weights)`,children:[(0,G.jsx)(`input`,{type:`checkbox`,checked:e.balance??!1,onChange:e=>s({balance:e.target.checked})}),` balanced`]}),a===`distance`&&(0,G.jsx)(ni,{stat:e.stat??`median`,multi:lt(c),onStat:e=>s({stat:e}),threshold:(0,G.jsx)(`input`,{className:`num`,type:`number`,step:`any`,min:0,placeholder:`threshold`,value:e.threshold??``,onChange:e=>s({threshold:e.target.value===``?null:Math.max(0,+e.target.value)}),title:`Distance threshold (${t?.xyz_unit??`dataset unit`}); empty = server default`})})]}):null}function Wi({pane:e}){let t=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)),n=gr(e),r=mr(n.kind===`group`?n.group:null),{locus:i,setLocus:a}=ti(),o=(0,g.useRef)(null),s=(0,g.useRef)(null),c=br(o),l=t?.contact_maps??[],u=Hi(e,l,t?.has_coords!==!1&&(t?.n_spots??0)>0),d=l.find(e=>e.key===u),[f,p]=(0,g.useState)(null),[m,h]=(0,g.useState)(null),[_,v]=(0,g.useState)(!1),[y,b]=(0,g.useState)(null),[x,S]=(0,g.useState)(null),C=!!d?.per_cell,w=C||u===`distance`,T=si(),E=w&&n.kind===`cell`?n.cell:null,D=w&&n.kind===`group`?n.group:C&&n.kind===`all`?`all`:null;(0,g.useEffect)(()=>{if(!t||!i||!u)return;let n=!0,r=setTimeout(()=>{v(!0),(u===`distance`?Fe(t.id,i,{cellId:E,group:D,stat:e.stat??`median`,threshold:e.threshold??null}):Pe(t.id,u,i,{resolution:e.resolution??null,balance:e.balance??!1,cell:E,group:D})).then(e=>n&&(p(e),h(null))).catch(e=>n&&(h(e.message),p(null))).finally(()=>n&&v(!1))},200);return()=>{n=!1,clearTimeout(r)}},[t?.id,u,i?.chrom,i?.start,i?.end,E,D,e.stat,e.threshold,e.resolution,e.balance,!1]);let O=f?oe(f.header.value):`contacts`,k=(0,g.useMemo)(()=>f?ce(f.data,O):[0,1],[f,O]),A=(0,g.useMemo)(()=>{if(!f||!f.header.n_rows||!f.header.n_cols)return null;let e=document.createElement(`canvas`);return e.width=f.header.n_cols,e.height=f.header.n_rows,e.getContext(`2d`).putImageData(new ImageData(pe(f,O,k),e.width,e.height),0,0),e},[f,O,k]),j=Math.max(0,Math.min(c.w-Vi.left-Vi.right,c.h-Vi.top-Vi.bottom)),M=f?.header.n_cols??0;(0,g.useEffect)(()=>{let e=s.current;if(!e||!c.w||!c.h)return;let t=xr(e,c.w,c.h);if(!t||!f||!A||j<20)return;t.imageSmoothingEnabled=!1,t.drawImage(A,Vi.left,Vi.top,j,j),t.strokeStyle=li.axis,t.strokeRect(Vi.left-.5,Vi.top-.5,j+1,j+1);let n=f.header;t.font=li.font,t.fillStyle=li.text;let r=Math.max(2,Math.min(6,Math.floor(j/80)));for(let e=0;e<=r;e++){let i=Math.min(M-1,Math.round(e/r*(M-1))),a=(i+.5)/M*j,o=$r(n.bin_starts[i]);t.textAlign=`center`,t.textBaseline=`top`;let s=t.measureText(o).width/2;t.fillText(o,Math.min(Vi.left+a,c.w-2-s),Vi.top+j+4),t.textAlign=`right`,t.textBaseline=`middle`,t.fillText(o,Vi.left-4,Vi.top+a)}if(x){let e=Math.min(x.i0,x.i1),n=Math.max(x.i0,x.i1)+1;t.strokeStyle=`#ffffff`,t.setLineDash([4,3]),t.strokeRect(Vi.left+e/M*j,Vi.top+e/M*j,(n-e)/M*j,(n-e)/M*j),t.setLineDash([])}let i=n.unit?` (${n.unit})`:``,a=O===`contacts`?`${n.value===`balanced`?`balanced`:`contacts`} (log)`:O===`distance`?`distance${i}`:`contact frequency`,o=O===`contacts`?`0`:$r(k[0]),l=O===`contacts`?`≥${$r(Math.expm1(k[1]))}`:$r(k[1]);di(t,{x:Vi.left,y:Vi.top+j+34,w:Math.min(180,j),h:8},e=>fi(fe(O===`contacts`?Math.expm1(e*k[1]):k[0]+e*(k[1]-k[0]),O,k)),o,l,a)},[f,A,j,c.w,c.h,x,k,O,M]);let N=(e,t)=>{let n=(e.clientX-t.left-Vi.left)/j,r=(e.clientY-t.top-Vi.top)/j;return[Math.floor(n*M),Math.floor(r*M)]},P=(e,t)=>e>=0&&t>=0&&e<M&&t<M,F=e=>{if(!f||e.buttons)return;let t=e.currentTarget.getBoundingClientRect(),[n,r]=N(e,t);if(!P(n,r))return b(null);let i=f.header,a=f.data[r*i.n_cols+n];b({x:e.clientX-t.left,y:e.clientY-t.top,text:`${i.chrom}:${H(i.bin_starts[r])} × ${H(i.bin_starts[n])} · ${Number.isFinite(a)?$r(a):`—`}${i.unit&&O===`distance`?` ${i.unit}`:``}`})},ee=e=>{if(!f||!i)return;let t=e.currentTarget.getBoundingClientRect(),[n]=N(e,t);if(!P(n,n))return;let r={i0:n,i1:n};S(r);let o=e=>{let[i]=N(e,t);r={i0:n,i1:Math.max(0,Math.min(M-1,i))},S(r),b(null)},s=()=>{window.removeEventListener(`pointermove`,o),window.removeEventListener(`pointerup`,s),S(null);let e=Math.min(r.i0,r.i1),t=Math.max(r.i0,r.i1);t-e>=1&&a({chrom:f.header.chrom,start:f.header.bin_starts[e],end:f.header.bin_ends[t]})};window.addEventListener(`pointermove`,o),window.addEventListener(`pointerup`,s)},te=null;u?i||(te=`No chromosomes to show.`):te=`No contact maps and no 3-D coordinates — nothing to show as a matrix.`;let I=[f?.header.note,f?.header.n_cells&&D?`${f.header.n_cells} cells used`:null,f?.header.n_contacts?`${$r(f.header.n_contacts)} contacts (pseudo-bulk)`:null,f?.header.n_traces?`${f.header.n_traces} traces`:null,f?.header.resolution?`${H(f.header.resolution)} bins`:null].filter(Boolean).join(` · `);return(0,G.jsxs)(`div`,{ref:o,className:`genome-view`,children:[te&&(0,G.jsx)(`div`,{className:`muted pane-empty`,children:te}),m&&!te&&(0,G.jsx)(`div`,{className:`error pane-error`,children:m}),(0,G.jsx)(`canvas`,{ref:s,onPointerDown:ee,onMouseMove:F,onMouseLeave:()=>b(null),style:{cursor:`crosshair`}}),_&&(0,G.jsx)(`div`,{className:`pane-loading muted small`,children:`loading…`}),w?(0,G.jsxs)(`div`,{className:`pane-badge small`,children:[n.kind===`group`&&(0,G.jsx)(`span`,{className:`swatch round`,style:{display:`inline-block`,width:8,height:8,marginRight:4,background:r?.color??`#888`}}),mt(n,r,T)]}):d&&(0,G.jsx)(`div`,{className:`pane-badge small`,children:`bulk map (all cells in the file)`}),I&&!te&&(0,G.jsx)(`div`,{className:`matrix-note muted small`,style:{left:Vi.left,top:Vi.top+j+58},children:I}),y&&(0,G.jsx)(`div`,{className:`embedding-tip`,style:{left:Math.min(y.x+12,c.w-240),top:y.y+12},children:y.text})]})}var Gi={region:`Region`,trace:`Trace`};function Ki(){let e=W(e=>e.datasets),t=W(e=>e.activeDatasetId),n=W(e=>e.layers),r=W(e=>e.selectedLayerId),i=e.find(e=>e.id===t),a=n.find(e=>e.id===r&&e.datasetId===t)??n.find(e=>e.datasetId===t&&e.parentId===null),o=(0,g.useMemo)(()=>{if(!i||!a)return[];let e=[`region`];return i.trace_mode&&e.push(`trace`),e},[i,a]),[s,c]=(0,g.useState)(null),l=s&&o.includes(s)?s:o[0];return!i||!a?null:(0,G.jsxs)(`details`,{className:`panel subset`,children:[(0,G.jsx)(`summary`,{children:(0,G.jsx)(`h2`,{children:`Subset layer`})}),(0,G.jsxs)(`div`,{className:`muted small`,children:[`new layer from `,(0,G.jsx)(`b`,{children:a.name}),` — for comparing or exporting a region / set of traces`]}),(0,G.jsx)(`div`,{className:`tabs`,children:o.map(e=>(0,G.jsx)(`button`,{className:e===l?`active`:``,onClick:()=>c(e),children:Gi[e]},e))}),l===`region`&&(0,G.jsx)(Ji,{ds:i,parent:a}),l===`trace`&&(0,G.jsx)(Xi,{ds:i,parent:a})]})}function qi(e,t){let n=W(e=>e.addLayer),[r,i]=(0,g.useState)(null);return{create:(r,a,o)=>{let s=kt(t.filter,r);if(!s){i(`Empty selection: ${jt(r)} does not overlap ${t.name}`);return}i(null),n({datasetId:e.id,parentId:t.id,name:a??jt(r),filter:s,style:{...t.style,...o}})},error:r,setError:i}}function Ji({ds:e,parent:t}){let n=At(t.filter,e.chroms),[r,i]=(0,g.useState)(n[0]?.name??``),[a,o]=(0,g.useState)(``),{create:s,error:c,setError:l}=qi(e,t),u=n.find(e=>e.name===r)??n[0];if(!u)return null;let d=t.filter.region?.chrom===u.name?Math.max(u.start,t.filter.region.start):u.start,f=t.filter.region?.chrom===u.name?Math.min(u.end,t.filter.region.end):u.end,p=()=>{try{s({region:Tt({...u,start:d,end:f},a)})}catch(e){l(e.message)}};return(0,G.jsxs)(`form`,{className:`op`,onSubmit:e=>{e.preventDefault(),p()},children:[(0,G.jsx)(`select`,{value:u.name,onChange:e=>i(e.target.value),children:n.map(e=>(0,G.jsx)(`option`,{children:e.name},e.name))}),(0,G.jsx)(`input`,{placeholder:`start-end, e.g. 10M-20M`,value:a,onChange:e=>o(e.target.value)}),(0,G.jsxs)(`div`,{className:`muted small`,children:[`valid: `,H(d),`-`,H(f)]}),(0,G.jsx)(`button`,{type:`submit`,disabled:!a.trim(),children:`Create subset`}),c&&(0,G.jsx)(`div`,{className:`error`,children:c})]})}var Yi=500;function Xi({ds:e,parent:t}){let n=At(t.filter,e.chroms),[r,i]=(0,g.useState)(n.length===1?n[0].name:``),[a,o]=(0,g.useState)([]),[s,c]=(0,g.useState)(0),[l,u]=(0,g.useState)(``),[d,f]=(0,g.useState)(!1),{create:p,error:m,setError:h}=qi(e,t),_=async t=>{f(!0);try{let n=await R(e.id,{chrom:r||void 0,offset:t,limit:Yi});c(n.total),o(e=>t===0?n.traces:[...e,...n.traces])}catch(e){h(e.message)}finally{f(!1)}};(0,g.useEffect)(()=>{o([]),_(0)},[e.id,r]);let v=t.filter.trace_ids?a.filter(e=>t.filter.trace_ids.includes(e.trace_id)):a,y=v.map(e=>e.trace_id),b=()=>{try{let e=Et(l,y);p({trace_ids:e},e.length===1?`trace ${e[0]}`:`${l.trim()} (${e.length} traces)`)}catch(e){h(e.message)}};return(0,G.jsxs)(`form`,{className:`op`,onSubmit:e=>{e.preventDefault(),b()},children:[(0,G.jsxs)(`select`,{value:r,onChange:e=>i(e.target.value),children:[n.length>1&&(0,G.jsx)(`option`,{value:``,children:`all chromosomes`}),n.map(e=>(0,G.jsx)(`option`,{children:e.name},e.name))]}),(0,G.jsx)(`ul`,{className:`trace-list`,children:v.map((e,t)=>(0,G.jsxs)(`li`,{onClick:()=>u(e.trace_id),title:`${e.chrom}:${H(e.start)}-${H(e.end)}`,children:[(0,G.jsx)(`span`,{className:`idx`,children:t+1}),` `,e.trace_id,(0,G.jsxs)(`span`,{className:`muted`,children:[` `,e.cell_id===null?``:`cell ${e.cell_id} · `,e.n_spots,` spots`]})]},e.trace_id))}),a.length<s&&(0,G.jsx)(`button`,{type:`button`,disabled:d,onClick:()=>void _(a.length),children:d?`Loading…`:`Load more (${a.length}/${s})`}),(0,G.jsx)(`input`,{placeholder:`id, "1-50", or "t1, t7, 3-5"`,value:l,onChange:e=>u(e.target.value)}),(0,G.jsx)(`button`,{type:`submit`,disabled:!l.trim(),children:`Create subset`}),m&&(0,G.jsx)(`div`,{className:`error`,children:m})]})}var Zi={LEFT:0,MIDDLE:1,RIGHT:2,ROTATE:0,DOLLY:1,PAN:2},Qi=1e3,$i=1001,ea=1002,ta=1003,na=1004,ra=1005,ia=1006,aa=1007,oa=1008,sa=1009,ca=1010,la=1011,ua=1012,da=1013,fa=1014,pa=1015,ma=1016,ha=1017,ga=1018,_a=1020,va=35902,ya=35899,ba=1021,xa=1022,Sa=1023,Ca=1026,wa=1027,Ta=1028,Ea=1029,Da=1030,Oa=1031,ka=1033,Aa=33776,ja=33777,Ma=33778,Na=33779,Pa=35840,Fa=35841,Ia=35842,La=35843,Ra=36196,za=37492,Ba=37496,Va=37488,Ha=37489,Ua=37490,Wa=37491,Ga=37808,Ka=37809,qa=37810,Ja=37811,Ya=37812,Xa=37813,Za=37814,Qa=37815,$a=37816,eo=37817,to=37818,no=37819,ro=37820,io=37821,ao=36492,oo=36494,so=36495,co=36283,lo=36284,uo=36285,fo=36286,po=2300,mo=2301,ho=2302,go=2303,_o=2400,vo=2401,yo=2402,bo=3200,xo=`srgb`,So=`srgb-linear`,Co=`linear`,wo=`srgb`,To=7680,Eo=35044,Do=2e3;function Oo(e){for(let t=e.length-1;t>=0;--t)if(e[t]>=65535)return!0;return!1}function ko(e){return ArrayBuffer.isView(e)&&!(e instanceof DataView)}function Ao(e){return document.createElementNS(`http://www.w3.org/1999/xhtml`,e)}function jo(){let e=Ao(`canvas`);return e.style.display=`block`,e}var Mo={};function No(...e){let t=`THREE.`+e.shift();console.log(t,...e)}function Po(e){let t=e[0];if(typeof t==`string`&&t.startsWith(`TSL:`)){let t=e[1];t&&t.isStackTrace?e[0]+=` `+t.getLocation():e[1]=`Stack trace not available. Enable "THREE.Node.captureStackTrace" to capture stack traces.`}return e}function K(...e){e=Po(e);let t=`THREE.`+e.shift();{let n=e[0];n&&n.isStackTrace?console.warn(n.getError(t)):console.warn(t,...e)}}function q(...e){e=Po(e);let t=`THREE.`+e.shift();{let n=e[0];n&&n.isStackTrace?console.error(n.getError(t)):console.error(t,...e)}}function Fo(...e){let t=e.join(` `);t in Mo||(Mo[t]=!0,K(...e))}function Io(e,t,n){return new Promise(function(r,i){function a(){switch(e.clientWaitSync(t,e.SYNC_FLUSH_COMMANDS_BIT,0)){case e.WAIT_FAILED:i();break;case e.TIMEOUT_EXPIRED:setTimeout(a,n);break;default:r()}}setTimeout(a,n)})}var Lo={0:1,2:6,4:7,3:5,1:0,6:2,7:4,5:3},Ro=class{addEventListener(e,t){this._listeners===void 0&&(this._listeners={});let n=this._listeners;n[e]===void 0&&(n[e]=[]),n[e].indexOf(t)===-1&&n[e].push(t)}hasEventListener(e,t){let n=this._listeners;return n!==void 0&&n[e]!==void 0&&n[e].indexOf(t)!==-1}removeEventListener(e,t){let n=this._listeners;if(n===void 0)return;let r=n[e];if(r!==void 0){let e=r.indexOf(t);e!==-1&&r.splice(e,1)}}dispatchEvent(e){let t=this._listeners;if(t===void 0)return;let n=t[e.type];if(n!==void 0){e.target=this;let t=n.slice(0);for(let n=0,r=t.length;n<r;n++)t[n].call(this,e);e.target=null}}},zo=`00.01.02.03.04.05.06.07.08.09.0a.0b.0c.0d.0e.0f.10.11.12.13.14.15.16.17.18.19.1a.1b.1c.1d.1e.1f.20.21.22.23.24.25.26.27.28.29.2a.2b.2c.2d.2e.2f.30.31.32.33.34.35.36.37.38.39.3a.3b.3c.3d.3e.3f.40.41.42.43.44.45.46.47.48.49.4a.4b.4c.4d.4e.4f.50.51.52.53.54.55.56.57.58.59.5a.5b.5c.5d.5e.5f.60.61.62.63.64.65.66.67.68.69.6a.6b.6c.6d.6e.6f.70.71.72.73.74.75.76.77.78.79.7a.7b.7c.7d.7e.7f.80.81.82.83.84.85.86.87.88.89.8a.8b.8c.8d.8e.8f.90.91.92.93.94.95.96.97.98.99.9a.9b.9c.9d.9e.9f.a0.a1.a2.a3.a4.a5.a6.a7.a8.a9.aa.ab.ac.ad.ae.af.b0.b1.b2.b3.b4.b5.b6.b7.b8.b9.ba.bb.bc.bd.be.bf.c0.c1.c2.c3.c4.c5.c6.c7.c8.c9.ca.cb.cc.cd.ce.cf.d0.d1.d2.d3.d4.d5.d6.d7.d8.d9.da.db.dc.dd.de.df.e0.e1.e2.e3.e4.e5.e6.e7.e8.e9.ea.eb.ec.ed.ee.ef.f0.f1.f2.f3.f4.f5.f6.f7.f8.f9.fa.fb.fc.fd.fe.ff`.split(`.`),Bo=1234567,Vo=Math.PI/180,Ho=180/Math.PI;function Uo(){let e=Math.random()*4294967295|0,t=Math.random()*4294967295|0,n=Math.random()*4294967295|0,r=Math.random()*4294967295|0;return(zo[e&255]+zo[e>>8&255]+zo[e>>16&255]+zo[e>>24&255]+`-`+zo[t&255]+zo[t>>8&255]+`-`+zo[t>>16&15|64]+zo[t>>24&255]+`-`+zo[n&63|128]+zo[n>>8&255]+`-`+zo[n>>16&255]+zo[n>>24&255]+zo[r&255]+zo[r>>8&255]+zo[r>>16&255]+zo[r>>24&255]).toLowerCase()}function J(e,t,n){return Math.max(t,Math.min(n,e))}function Wo(e,t){return(e%t+t)%t}function Go(e,t,n,r,i){return r+(e-t)*(i-r)/(n-t)}function Ko(e,t,n){return e===t?0:(n-e)/(t-e)}function qo(e,t,n){return(1-n)*e+n*t}function Jo(e,t,n,r){return qo(e,t,1-Math.exp(-n*r))}function Yo(e,t=1){return t-Math.abs(Wo(e,t*2)-t)}function Xo(e,t,n){return e<=t?0:e>=n?1:(e=(e-t)/(n-t),e*e*(3-2*e))}function Zo(e,t,n){return e<=t?0:e>=n?1:(e=(e-t)/(n-t),e*e*e*(e*(e*6-15)+10))}function Qo(e,t){return e+Math.floor(Math.random()*(t-e+1))}function $o(e,t){return e+Math.random()*(t-e)}function es(e){return e*(.5-Math.random())}function ts(e){e!==void 0&&(Bo=e);let t=Bo+=1831565813;return t=Math.imul(t^t>>>15,t|1),t^=t+Math.imul(t^t>>>7,t|61),((t^t>>>14)>>>0)/4294967296}function ns(e){return e*Vo}function rs(e){return e*Ho}function is(e){return e>0&&Number.isInteger(e)&&2**Math.round(Math.log2(e))===e}function as(e){return 2**Math.ceil(Math.log(e)/Math.LN2)}function os(e){return 2**Math.floor(Math.log(e)/Math.LN2)}function ss(e,t,n,r,i){let a=Math.cos,o=Math.sin,s=a(n/2),c=o(n/2),l=a((t+r)/2),u=o((t+r)/2),d=a((t-r)/2),f=o((t-r)/2),p=a((r-t)/2),m=o((r-t)/2);switch(i){case`XYX`:e.set(s*u,c*d,c*f,s*l);break;case`YZY`:e.set(c*f,s*u,c*d,s*l);break;case`ZXZ`:e.set(c*d,c*f,s*u,s*l);break;case`XZX`:e.set(s*u,c*m,c*p,s*l);break;case`YXY`:e.set(c*p,s*u,c*m,s*l);break;case`ZYZ`:e.set(c*m,c*p,s*u,s*l);break;default:K(`MathUtils: .setQuaternionFromProperEuler() encountered an unknown order: `+i)}}function cs(e,t){switch(t.constructor){case Float32Array:return e;case Uint32Array:return e/4294967295;case Uint16Array:return e/65535;case Uint8Array:case Uint8ClampedArray:return e/255;case Int32Array:return Math.max(e/2147483647,-1);case Int16Array:return Math.max(e/32767,-1);case Int8Array:return Math.max(e/127,-1);default:throw Error(`THREE.MathUtils: Invalid component type.`)}}function ls(e,t){switch(t.constructor){case Float32Array:return e;case Uint32Array:return Math.round(e*4294967295);case Uint16Array:return Math.round(e*65535);case Uint8Array:case Uint8ClampedArray:return Math.round(e*255);case Int32Array:return Math.round(e*2147483647);case Int16Array:return Math.round(e*32767);case Int8Array:return Math.round(e*127);default:throw Error(`THREE.MathUtils: Invalid component type.`)}}var us={DEG2RAD:Vo,RAD2DEG:Ho,generateUUID:Uo,clamp:J,euclideanModulo:Wo,mapLinear:Go,inverseLerp:Ko,lerp:qo,damp:Jo,pingpong:Yo,smoothstep:Xo,smootherstep:Zo,randInt:Qo,randFloat:$o,randFloatSpread:es,seededRandom:ts,degToRad:ns,radToDeg:rs,isPowerOfTwo:is,ceilPowerOfTwo:as,floorPowerOfTwo:os,setQuaternionFromProperEuler:ss,normalize:ls,denormalize:cs},Y=class e{static{e.prototype.isVector2=!0}constructor(e=0,t=0){this.x=e,this.y=t}get width(){return this.x}set width(e){this.x=e}get height(){return this.y}set height(e){this.y=e}set(e,t){return this.x=e,this.y=t,this}setScalar(e){return this.x=e,this.y=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;default:throw Error(`THREE.Vector2: index is out of range: `+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;default:throw Error(`THREE.Vector2: index is out of range: `+e)}}clone(){return new this.constructor(this.x,this.y)}copy(e){return this.x=e.x,this.y=e.y,this}add(e){return this.x+=e.x,this.y+=e.y,this}addScalar(e){return this.x+=e,this.y+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this}subScalar(e){return this.x-=e,this.y-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this}multiply(e){return this.x*=e.x,this.y*=e.y,this}multiplyScalar(e){return this.x*=e,this.y*=e,this}divide(e){return this.x/=e.x,this.y/=e.y,this}divideScalar(e){return this.multiplyScalar(1/e)}applyMatrix3(e){let t=this.x,n=this.y,r=e.elements;return this.x=r[0]*t+r[3]*n+r[6],this.y=r[1]*t+r[4]*n+r[7],this}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this}clamp(e,t){return this.x=J(this.x,e.x,t.x),this.y=J(this.y,e.y,t.y),this}clampScalar(e,t){return this.x=J(this.x,e,t),this.y=J(this.y,e,t),this}clampLength(e,t){let n=this.length();return this.divideScalar(n||1).multiplyScalar(J(n,e,t))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this}negate(){return this.x=-this.x,this.y=-this.y,this}dot(e){return this.x*e.x+this.y*e.y}cross(e){return this.x*e.y-this.y*e.x}lengthSq(){return this.x*this.x+this.y*this.y}length(){return Math.sqrt(this.x*this.x+this.y*this.y)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)}normalize(){return this.divideScalar(this.length()||1)}angle(){return Math.atan2(-this.y,-this.x)+Math.PI}angleTo(e){let t=Math.sqrt(this.lengthSq()*e.lengthSq());if(t===0)return Math.PI/2;let n=this.dot(e)/t;return Math.acos(J(n,-1,1))}distanceTo(e){return Math.sqrt(this.distanceToSquared(e))}distanceToSquared(e){let t=this.x-e.x,n=this.y-e.y;return t*t+n*n}manhattanDistanceTo(e){return Math.abs(this.x-e.x)+Math.abs(this.y-e.y)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this}equals(e){return e.x===this.x&&e.y===this.y}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this}rotateAround(e,t){let n=Math.cos(t),r=Math.sin(t),i=this.x-e.x,a=this.y-e.y;return this.x=i*n-a*r+e.x,this.y=i*r+a*n+e.y,this}random(){return this.x=Math.random(),this.y=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y}},ds=class{constructor(e=0,t=0,n=0,r=1){this.isQuaternion=!0,this._x=e,this._y=t,this._z=n,this._w=r}static slerpFlat(e,t,n,r,i,a,o){let s=n[r+0],c=n[r+1],l=n[r+2],u=n[r+3],d=i[a+0],f=i[a+1],p=i[a+2],m=i[a+3];if(u!==m||s!==d||c!==f||l!==p){let e=s*d+c*f+l*p+u*m;e<0&&(d=-d,f=-f,p=-p,m=-m,e=-e);let t=1-o;if(e<.9995){let n=Math.acos(e),r=Math.sin(n);t=Math.sin(t*n)/r,o=Math.sin(o*n)/r,s=s*t+d*o,c=c*t+f*o,l=l*t+p*o,u=u*t+m*o}else{s=s*t+d*o,c=c*t+f*o,l=l*t+p*o,u=u*t+m*o;let e=1/Math.sqrt(s*s+c*c+l*l+u*u);s*=e,c*=e,l*=e,u*=e}}e[t]=s,e[t+1]=c,e[t+2]=l,e[t+3]=u}static multiplyQuaternionsFlat(e,t,n,r,i,a){let o=n[r],s=n[r+1],c=n[r+2],l=n[r+3],u=i[a],d=i[a+1],f=i[a+2],p=i[a+3];return e[t]=o*p+l*u+s*f-c*d,e[t+1]=s*p+l*d+c*u-o*f,e[t+2]=c*p+l*f+o*d-s*u,e[t+3]=l*p-o*u-s*d-c*f,e}get x(){return this._x}set x(e){this._x=e,this._onChangeCallback()}get y(){return this._y}set y(e){this._y=e,this._onChangeCallback()}get z(){return this._z}set z(e){this._z=e,this._onChangeCallback()}get w(){return this._w}set w(e){this._w=e,this._onChangeCallback()}set(e,t,n,r){return this._x=e,this._y=t,this._z=n,this._w=r,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._w)}copy(e){return this._x=e.x,this._y=e.y,this._z=e.z,this._w=e.w,this._onChangeCallback(),this}setFromEuler(e,t=!0){let n=e._x,r=e._y,i=e._z,a=e._order,o=Math.cos,s=Math.sin,c=o(n/2),l=o(r/2),u=o(i/2),d=s(n/2),f=s(r/2),p=s(i/2);switch(a){case`XYZ`:this._x=d*l*u+c*f*p,this._y=c*f*u-d*l*p,this._z=c*l*p+d*f*u,this._w=c*l*u-d*f*p;break;case`YXZ`:this._x=d*l*u+c*f*p,this._y=c*f*u-d*l*p,this._z=c*l*p-d*f*u,this._w=c*l*u+d*f*p;break;case`ZXY`:this._x=d*l*u-c*f*p,this._y=c*f*u+d*l*p,this._z=c*l*p+d*f*u,this._w=c*l*u-d*f*p;break;case`ZYX`:this._x=d*l*u-c*f*p,this._y=c*f*u+d*l*p,this._z=c*l*p-d*f*u,this._w=c*l*u+d*f*p;break;case`YZX`:this._x=d*l*u+c*f*p,this._y=c*f*u+d*l*p,this._z=c*l*p-d*f*u,this._w=c*l*u-d*f*p;break;case`XZY`:this._x=d*l*u-c*f*p,this._y=c*f*u-d*l*p,this._z=c*l*p+d*f*u,this._w=c*l*u+d*f*p;break;default:K(`Quaternion: .setFromEuler() encountered an unknown order: `+a)}return t===!0&&this._onChangeCallback(),this}setFromAxisAngle(e,t){let n=t/2,r=Math.sin(n);return this._x=e.x*r,this._y=e.y*r,this._z=e.z*r,this._w=Math.cos(n),this._onChangeCallback(),this}setFromRotationMatrix(e){let t=e.elements,n=t[0],r=t[4],i=t[8],a=t[1],o=t[5],s=t[9],c=t[2],l=t[6],u=t[10],d=n+o+u;if(d>0){let e=.5/Math.sqrt(d+1);this._w=.25/e,this._x=(l-s)*e,this._y=(i-c)*e,this._z=(a-r)*e}else if(n>o&&n>u){let e=2*Math.sqrt(1+n-o-u);this._w=(l-s)/e,this._x=.25*e,this._y=(r+a)/e,this._z=(i+c)/e}else if(o>u){let e=2*Math.sqrt(1+o-n-u);this._w=(i-c)/e,this._x=(r+a)/e,this._y=.25*e,this._z=(s+l)/e}else{let e=2*Math.sqrt(1+u-n-o);this._w=(a-r)/e,this._x=(i+c)/e,this._y=(s+l)/e,this._z=.25*e}return this._onChangeCallback(),this}setFromUnitVectors(e,t){let n=e.dot(t)+1;return n<1e-8?(n=0,Math.abs(e.x)>Math.abs(e.z)?(this._x=-e.y,this._y=e.x,this._z=0,this._w=n):(this._x=0,this._y=-e.z,this._z=e.y,this._w=n)):(this._x=e.y*t.z-e.z*t.y,this._y=e.z*t.x-e.x*t.z,this._z=e.x*t.y-e.y*t.x,this._w=n),this.normalize()}angleTo(e){return 2*Math.acos(Math.abs(J(this.dot(e),-1,1)))}rotateTowards(e,t){let n=this.angleTo(e);if(n===0)return this;let r=Math.min(1,t/n);return this.slerp(e,r),this}identity(){return this.set(0,0,0,1)}invert(){return this.conjugate()}conjugate(){return this._x*=-1,this._y*=-1,this._z*=-1,this._onChangeCallback(),this}dot(e){return this._x*e._x+this._y*e._y+this._z*e._z+this._w*e._w}lengthSq(){return this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w}length(){return Math.sqrt(this._x*this._x+this._y*this._y+this._z*this._z+this._w*this._w)}normalize(){let e=this.length();return e===0?(this._x=0,this._y=0,this._z=0,this._w=1):(e=1/e,this._x*=e,this._y*=e,this._z*=e,this._w*=e),this._onChangeCallback(),this}multiply(e){return this.multiplyQuaternions(this,e)}premultiply(e){return this.multiplyQuaternions(e,this)}multiplyQuaternions(e,t){let n=e._x,r=e._y,i=e._z,a=e._w,o=t._x,s=t._y,c=t._z,l=t._w;return this._x=n*l+a*o+r*c-i*s,this._y=r*l+a*s+i*o-n*c,this._z=i*l+a*c+n*s-r*o,this._w=a*l-n*o-r*s-i*c,this._onChangeCallback(),this}slerp(e,t){let n=e._x,r=e._y,i=e._z,a=e._w,o=this.dot(e);o<0&&(n=-n,r=-r,i=-i,a=-a,o=-o);let s=1-t;if(o<.9995){let e=Math.acos(o),c=Math.sin(e);s=Math.sin(s*e)/c,t=Math.sin(t*e)/c,this._x=this._x*s+n*t,this._y=this._y*s+r*t,this._z=this._z*s+i*t,this._w=this._w*s+a*t,this._onChangeCallback()}else this._x=this._x*s+n*t,this._y=this._y*s+r*t,this._z=this._z*s+i*t,this._w=this._w*s+a*t,this.normalize();return this}slerpQuaternions(e,t,n){return this.copy(e).slerp(t,n)}random(){let e=2*Math.PI*Math.random(),t=2*Math.PI*Math.random(),n=Math.random(),r=Math.sqrt(1-n),i=Math.sqrt(n);return this.set(r*Math.sin(e),r*Math.cos(e),i*Math.sin(t),i*Math.cos(t))}equals(e){return e._x===this._x&&e._y===this._y&&e._z===this._z&&e._w===this._w}fromArray(e,t=0){return this._x=e[t],this._y=e[t+1],this._z=e[t+2],this._w=e[t+3],this._onChangeCallback(),this}toArray(e=[],t=0){return e[t]=this._x,e[t+1]=this._y,e[t+2]=this._z,e[t+3]=this._w,e}fromBufferAttribute(e,t){return this._x=e.getX(t),this._y=e.getY(t),this._z=e.getZ(t),this._w=e.getW(t),this._onChangeCallback(),this}toJSON(){return this.toArray()}_onChange(e){return this._onChangeCallback=e,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._w}},X=class e{static{e.prototype.isVector3=!0}constructor(e=0,t=0,n=0){this.x=e,this.y=t,this.z=n}set(e,t,n){return n===void 0&&(n=this.z),this.x=e,this.y=t,this.z=n,this}setScalar(e){return this.x=e,this.y=e,this.z=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setZ(e){return this.z=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;case 2:this.z=t;break;default:throw Error(`THREE.Vector3: index is out of range: `+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;case 2:return this.z;default:throw Error(`THREE.Vector3: index is out of range: `+e)}}clone(){return new this.constructor(this.x,this.y,this.z)}copy(e){return this.x=e.x,this.y=e.y,this.z=e.z,this}add(e){return this.x+=e.x,this.y+=e.y,this.z+=e.z,this}addScalar(e){return this.x+=e,this.y+=e,this.z+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this.z=e.z+t.z,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this.z+=e.z*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this.z-=e.z,this}subScalar(e){return this.x-=e,this.y-=e,this.z-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this.z=e.z-t.z,this}multiply(e){return this.x*=e.x,this.y*=e.y,this.z*=e.z,this}multiplyScalar(e){return this.x*=e,this.y*=e,this.z*=e,this}multiplyVectors(e,t){return this.x=e.x*t.x,this.y=e.y*t.y,this.z=e.z*t.z,this}applyEuler(e){return this.applyQuaternion(ps.setFromEuler(e))}applyAxisAngle(e,t){return this.applyQuaternion(ps.setFromAxisAngle(e,t))}applyMatrix3(e){let t=this.x,n=this.y,r=this.z,i=e.elements;return this.x=i[0]*t+i[3]*n+i[6]*r,this.y=i[1]*t+i[4]*n+i[7]*r,this.z=i[2]*t+i[5]*n+i[8]*r,this}applyNormalMatrix(e){return this.applyMatrix3(e).normalize()}applyMatrix4(e){let t=this.x,n=this.y,r=this.z,i=e.elements,a=1/(i[3]*t+i[7]*n+i[11]*r+i[15]);return this.x=(i[0]*t+i[4]*n+i[8]*r+i[12])*a,this.y=(i[1]*t+i[5]*n+i[9]*r+i[13])*a,this.z=(i[2]*t+i[6]*n+i[10]*r+i[14])*a,this}applyQuaternion(e){let t=this.x,n=this.y,r=this.z,i=e.x,a=e.y,o=e.z,s=e.w,c=2*(a*r-o*n),l=2*(o*t-i*r),u=2*(i*n-a*t);return this.x=t+s*c+a*u-o*l,this.y=n+s*l+o*c-i*u,this.z=r+s*u+i*l-a*c,this}project(e){return this.applyMatrix4(e.matrixWorldInverse).applyMatrix4(e.projectionMatrix)}unproject(e){return this.applyMatrix4(e.projectionMatrixInverse).applyMatrix4(e.matrixWorld)}transformDirection(e){let t=this.x,n=this.y,r=this.z,i=e.elements;return this.x=i[0]*t+i[4]*n+i[8]*r,this.y=i[1]*t+i[5]*n+i[9]*r,this.z=i[2]*t+i[6]*n+i[10]*r,this.normalize()}divide(e){return this.x/=e.x,this.y/=e.y,this.z/=e.z,this}divideScalar(e){return this.multiplyScalar(1/e)}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this.z=Math.min(this.z,e.z),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this.z=Math.max(this.z,e.z),this}clamp(e,t){return this.x=J(this.x,e.x,t.x),this.y=J(this.y,e.y,t.y),this.z=J(this.z,e.z,t.z),this}clampScalar(e,t){return this.x=J(this.x,e,t),this.y=J(this.y,e,t),this.z=J(this.z,e,t),this}clampLength(e,t){let n=this.length();return this.divideScalar(n||1).multiplyScalar(J(n,e,t))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this}dot(e){return this.x*e.x+this.y*e.y+this.z*e.z}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)}normalize(){return this.divideScalar(this.length()||1)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this.z+=(e.z-this.z)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this.z=e.z+(t.z-e.z)*n,this}cross(e){return this.crossVectors(this,e)}crossVectors(e,t){let n=e.x,r=e.y,i=e.z,a=t.x,o=t.y,s=t.z;return this.x=r*s-i*o,this.y=i*a-n*s,this.z=n*o-r*a,this}projectOnVector(e){let t=e.lengthSq();if(t===0)return this.set(0,0,0);let n=e.dot(this)/t;return this.copy(e).multiplyScalar(n)}projectOnPlane(e){return fs.copy(this).projectOnVector(e),this.sub(fs)}reflect(e){return this.sub(fs.copy(e).multiplyScalar(2*this.dot(e)))}angleTo(e){let t=Math.sqrt(this.lengthSq()*e.lengthSq());if(t===0)return Math.PI/2;let n=this.dot(e)/t;return Math.acos(J(n,-1,1))}distanceTo(e){return Math.sqrt(this.distanceToSquared(e))}distanceToSquared(e){let t=this.x-e.x,n=this.y-e.y,r=this.z-e.z;return t*t+n*n+r*r}manhattanDistanceTo(e){return Math.abs(this.x-e.x)+Math.abs(this.y-e.y)+Math.abs(this.z-e.z)}setFromSpherical(e){return this.setFromSphericalCoords(e.radius,e.phi,e.theta)}setFromSphericalCoords(e,t,n){let r=Math.sin(t)*e;return this.x=r*Math.sin(n),this.y=Math.cos(t)*e,this.z=r*Math.cos(n),this}setFromCylindrical(e){return this.setFromCylindricalCoords(e.radius,e.theta,e.y)}setFromCylindricalCoords(e,t,n){return this.x=e*Math.sin(t),this.y=n,this.z=e*Math.cos(t),this}setFromMatrixPosition(e){let t=e.elements;return this.x=t[12],this.y=t[13],this.z=t[14],this}setFromMatrixScale(e){let t=this.setFromMatrixColumn(e,0).length(),n=this.setFromMatrixColumn(e,1).length(),r=this.setFromMatrixColumn(e,2).length();return this.x=t,this.y=n,this.z=r,this}setFromMatrixColumn(e,t){return this.fromArray(e.elements,t*4)}setFromMatrix3Column(e,t){return this.fromArray(e.elements,t*3)}setFromEuler(e){return this.x=e._x,this.y=e._y,this.z=e._z,this}setFromColor(e){return this.x=e.r,this.y=e.g,this.z=e.b,this}equals(e){return e.x===this.x&&e.y===this.y&&e.z===this.z}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this.z=e[t+2],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e[t+2]=this.z,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this.z=e.getZ(t),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this}randomDirection(){let e=Math.random()*Math.PI*2,t=Math.random()*2-1,n=Math.sqrt(1-t*t);return this.x=n*Math.cos(e),this.y=t,this.z=n*Math.sin(e),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z}},fs=new X,ps=new ds,Z=class e{static{e.prototype.isMatrix3=!0}constructor(e,t,n,r,i,a,o,s,c){this.elements=[1,0,0,0,1,0,0,0,1],e!==void 0&&this.set(e,t,n,r,i,a,o,s,c)}set(e,t,n,r,i,a,o,s,c){let l=this.elements;return l[0]=e,l[1]=r,l[2]=o,l[3]=t,l[4]=i,l[5]=s,l[6]=n,l[7]=a,l[8]=c,this}identity(){return this.set(1,0,0,0,1,0,0,0,1),this}copy(e){let t=this.elements,n=e.elements;return t[0]=n[0],t[1]=n[1],t[2]=n[2],t[3]=n[3],t[4]=n[4],t[5]=n[5],t[6]=n[6],t[7]=n[7],t[8]=n[8],this}extractBasis(e,t,n){return e.setFromMatrix3Column(this,0),t.setFromMatrix3Column(this,1),n.setFromMatrix3Column(this,2),this}setFromMatrix4(e){let t=e.elements;return this.set(t[0],t[4],t[8],t[1],t[5],t[9],t[2],t[6],t[10]),this}multiply(e){return this.multiplyMatrices(this,e)}premultiply(e){return this.multiplyMatrices(e,this)}multiplyMatrices(e,t){let n=e.elements,r=t.elements,i=this.elements,a=n[0],o=n[3],s=n[6],c=n[1],l=n[4],u=n[7],d=n[2],f=n[5],p=n[8],m=r[0],h=r[3],g=r[6],_=r[1],v=r[4],y=r[7],b=r[2],x=r[5],S=r[8];return i[0]=a*m+o*_+s*b,i[3]=a*h+o*v+s*x,i[6]=a*g+o*y+s*S,i[1]=c*m+l*_+u*b,i[4]=c*h+l*v+u*x,i[7]=c*g+l*y+u*S,i[2]=d*m+f*_+p*b,i[5]=d*h+f*v+p*x,i[8]=d*g+f*y+p*S,this}multiplyScalar(e){let t=this.elements;return t[0]*=e,t[3]*=e,t[6]*=e,t[1]*=e,t[4]*=e,t[7]*=e,t[2]*=e,t[5]*=e,t[8]*=e,this}determinant(){let e=this.elements,t=e[0],n=e[1],r=e[2],i=e[3],a=e[4],o=e[5],s=e[6],c=e[7],l=e[8];return t*a*l-t*o*c-n*i*l+n*o*s+r*i*c-r*a*s}invert(){let e=this.elements,t=e[0],n=e[1],r=e[2],i=e[3],a=e[4],o=e[5],s=e[6],c=e[7],l=e[8],u=l*a-o*c,d=o*s-l*i,f=c*i-a*s,p=t*u+n*d+r*f;if(p===0)return this.set(0,0,0,0,0,0,0,0,0);let m=1/p;return e[0]=u*m,e[1]=(r*c-l*n)*m,e[2]=(o*n-r*a)*m,e[3]=d*m,e[4]=(l*t-r*s)*m,e[5]=(r*i-o*t)*m,e[6]=f*m,e[7]=(n*s-c*t)*m,e[8]=(a*t-n*i)*m,this}transpose(){let e,t=this.elements;return e=t[1],t[1]=t[3],t[3]=e,e=t[2],t[2]=t[6],t[6]=e,e=t[5],t[5]=t[7],t[7]=e,this}getNormalMatrix(e){return this.setFromMatrix4(e).invert().transpose()}transposeIntoArray(e){let t=this.elements;return e[0]=t[0],e[1]=t[3],e[2]=t[6],e[3]=t[1],e[4]=t[4],e[5]=t[7],e[6]=t[2],e[7]=t[5],e[8]=t[8],this}setUvTransform(e,t,n,r,i,a,o){let s=Math.cos(i),c=Math.sin(i);return this.set(n*s,n*c,-n*(s*a+c*o)+a+e,-r*c,r*s,-r*(-c*a+s*o)+o+t,0,0,1),this}scale(e,t){return Fo(`Matrix3: .scale() is deprecated. Use .makeScale() instead.`),this.premultiply(ms.makeScale(e,t)),this}rotate(e){return Fo(`Matrix3: .rotate() is deprecated. Use .makeRotation() instead.`),this.premultiply(ms.makeRotation(-e)),this}translate(e,t){return Fo(`Matrix3: .translate() is deprecated. Use .makeTranslation() instead.`),this.premultiply(ms.makeTranslation(e,t)),this}makeTranslation(e,t){return e.isVector2?this.set(1,0,e.x,0,1,e.y,0,0,1):this.set(1,0,e,0,1,t,0,0,1),this}makeRotation(e){let t=Math.cos(e),n=Math.sin(e);return this.set(t,-n,0,n,t,0,0,0,1),this}makeScale(e,t){return this.set(e,0,0,0,t,0,0,0,1),this}equals(e){let t=this.elements,n=e.elements;for(let e=0;e<9;e++)if(t[e]!==n[e])return!1;return!0}fromArray(e,t=0){for(let n=0;n<9;n++)this.elements[n]=e[n+t];return this}toArray(e=[],t=0){let n=this.elements;return e[t]=n[0],e[t+1]=n[1],e[t+2]=n[2],e[t+3]=n[3],e[t+4]=n[4],e[t+5]=n[5],e[t+6]=n[6],e[t+7]=n[7],e[t+8]=n[8],e}clone(){return new this.constructor().fromArray(this.elements)}},ms=new Z,hs=new Z().set(.4123908,.3575843,.1804808,.212639,.7151687,.0721923,.0193308,.1191948,.9505322),gs=new Z().set(3.2409699,-1.5373832,-.4986108,-.9692436,1.8759675,.0415551,.0556301,-.203977,1.0569715);function _s(){let e={enabled:!0,workingColorSpace:So,spaces:{},convert:function(e,t,n){return this.enabled===!1||t===n||!t||!n?e:(this.spaces[t].transfer===`srgb`&&(e.r=ys(e.r),e.g=ys(e.g),e.b=ys(e.b)),this.spaces[t].primaries!==this.spaces[n].primaries&&(e.applyMatrix3(this.spaces[t].toXYZ),e.applyMatrix3(this.spaces[n].fromXYZ)),this.spaces[n].transfer===`srgb`&&(e.r=bs(e.r),e.g=bs(e.g),e.b=bs(e.b)),e)},workingToColorSpace:function(e,t){return this.convert(e,this.workingColorSpace,t)},colorSpaceToWorking:function(e,t){return this.convert(e,t,this.workingColorSpace)},getPrimaries:function(e){return this.spaces[e].primaries},getTransfer:function(e){return e===``?Co:this.spaces[e].transfer},getToneMappingMode:function(e){return this.spaces[e].outputColorSpaceConfig.toneMappingMode||`standard`},getLuminanceCoefficients:function(e,t=this.workingColorSpace){return e.fromArray(this.spaces[t].luminanceCoefficients)},define:function(e){Object.assign(this.spaces,e)},_getMatrix:function(e,t,n){return e.copy(this.spaces[t].toXYZ).multiply(this.spaces[n].fromXYZ)},_getDrawingBufferColorSpace:function(e){return this.spaces[e].outputColorSpaceConfig.drawingBufferColorSpace},_getUnpackColorSpace:function(e=this.workingColorSpace){return this.spaces[e].workingColorSpaceConfig.unpackColorSpace},fromWorkingColorSpace:function(t,n){return Fo(`ColorManagement: .fromWorkingColorSpace() has been renamed to .workingToColorSpace().`),e.workingToColorSpace(t,n)},toWorkingColorSpace:function(t,n){return Fo(`ColorManagement: .toWorkingColorSpace() has been renamed to .colorSpaceToWorking().`),e.colorSpaceToWorking(t,n)}},t=[.64,.33,.3,.6,.15,.06],n=[.2126,.7152,.0722],r=[.3127,.329];return e.define({[So]:{primaries:t,whitePoint:r,transfer:Co,toXYZ:hs,fromXYZ:gs,luminanceCoefficients:n,workingColorSpaceConfig:{unpackColorSpace:xo},outputColorSpaceConfig:{drawingBufferColorSpace:xo}},[xo]:{primaries:t,whitePoint:r,transfer:wo,toXYZ:hs,fromXYZ:gs,luminanceCoefficients:n,outputColorSpaceConfig:{drawingBufferColorSpace:xo}}}),e}var vs=_s();function ys(e){return e<.04045?e*.0773993808:(e*.9478672986+.0521327014)**2.4}function bs(e){return e<.0031308?e*12.92:1.055*e**.41666-.055}var xs,Ss=class{static getDataURL(e,t=`image/png`){if(/^data:/i.test(e.src)||typeof HTMLCanvasElement>`u`)return e.src;let n;if(e instanceof HTMLCanvasElement)n=e;else{xs===void 0&&(xs=Ao(`canvas`)),xs.width=e.width,xs.height=e.height;let t=xs.getContext(`2d`);e instanceof ImageData?t.putImageData(e,0,0):t.drawImage(e,0,0,e.width,e.height),n=xs}return n.toDataURL(t)}static sRGBToLinear(e){if(typeof HTMLImageElement<`u`&&e instanceof HTMLImageElement||typeof HTMLCanvasElement<`u`&&e instanceof HTMLCanvasElement||typeof ImageBitmap<`u`&&e instanceof ImageBitmap){let t=Ao(`canvas`);t.width=e.width,t.height=e.height;let n=t.getContext(`2d`);n.drawImage(e,0,0,e.width,e.height);let r=n.getImageData(0,0,e.width,e.height),i=r.data;for(let e=0;e<i.length;e++)i[e]=ys(i[e]/255)*255;return n.putImageData(r,0,0),t}if(e.data){let t=e.data.slice(0);for(let e=0;e<t.length;e++)t instanceof Uint8Array||t instanceof Uint8ClampedArray?t[e]=Math.floor(ys(t[e]/255)*255):t[e]=ys(t[e]);return{data:t,width:e.width,height:e.height}}return K(`ImageUtils.sRGBToLinear(): Unsupported image type. No color space conversion applied.`),e}},Cs=0,ws=class{constructor(e=null){this.isTextureSource=!0,Object.defineProperty(this,"id",{value:Cs++}),this.uuid=Uo(),this.data=e,this.dataReady=!0,this.version=0}getSize(e){let t=this.data;return typeof HTMLVideoElement<`u`&&t instanceof HTMLVideoElement?e.set(t.videoWidth,t.videoHeight,0):typeof VideoFrame<`u`&&t instanceof VideoFrame?e.set(t.displayWidth,t.displayHeight,0):t===null?e.set(0,0,0):e.set(t.width,t.height,t.depth||0),e}set needsUpdate(e){e===!0&&this.version++}toJSON(e){let t=e===void 0||typeof e==`string`;if(!t&&e.images[this.uuid]!==void 0)return e.images[this.uuid];let n={uuid:this.uuid,url:``},r=this.data;if(r!==null){let e;if(Array.isArray(r)){e=[];for(let t=0,n=r.length;t<n;t++)r[t].isDataTexture?e.push(Ts(r[t].image)):e.push(Ts(r[t]))}else e=Ts(r);n.url=e}return t||(e.images[this.uuid]=n),n}};function Ts(e){return typeof HTMLImageElement<`u`&&e instanceof HTMLImageElement||typeof HTMLCanvasElement<`u`&&e instanceof HTMLCanvasElement||typeof ImageBitmap<`u`&&e instanceof ImageBitmap?Ss.getDataURL(e):e.data?{data:Array.from(e.data),width:e.width,height:e.height,type:e.data.constructor.name}:(K(`Texture: Unable to serialize Texture.`),{})}var Es=0,Ds=new X,Os=class e extends Ro{constructor(t=e.DEFAULT_IMAGE,n=e.DEFAULT_MAPPING,r=$i,i=$i,a=ia,o=oa,s=Sa,c=sa,l=e.DEFAULT_ANISOTROPY,u=``){super(),this.isTexture=!0,Object.defineProperty(this,"id",{value:Es++}),this.uuid=Uo(),this.name=``,this.source=new ws(t),this.mipmaps=[],this.mapping=n,this.channel=0,this.wrapS=r,this.wrapT=i,this.magFilter=a,this.minFilter=o,this.anisotropy=l,this.format=s,this.internalFormat=null,this.type=c,this.offset=new Y(0,0),this.repeat=new Y(1,1),this.center=new Y(0,0),this.rotation=0,this.matrixAutoUpdate=!0,this.matrix=new Z,this.generateMipmaps=!0,this.premultiplyAlpha=!1,this.flipY=!0,this.unpackAlignment=4,this.colorSpace=u,this.userData={},this.updateRanges=[],this.version=0,this.onUpdate=null,this.renderTarget=null,this.isRenderTargetTexture=!1,this.isArrayTexture=!!(t&&t.depth&&t.depth>1),this.pmremVersion=0,this.normalized=!1}get width(){return this.source.getSize(Ds).x}get height(){return this.source.getSize(Ds).y}get depth(){return this.source.getSize(Ds).z}get image(){return this.source.data}set image(e){this.source.data=e}updateMatrix(){this.matrix.setUvTransform(this.offset.x,this.offset.y,this.repeat.x,this.repeat.y,this.rotation,this.center.x,this.center.y)}addUpdateRange(e,t){this.updateRanges.push({start:e,count:t})}clearUpdateRanges(){this.updateRanges.length=0}clone(){return new this.constructor().copy(this)}copy(e){return this.name=e.name,this.source=e.source,this.mipmaps=e.mipmaps.slice(0),this.mapping=e.mapping,this.channel=e.channel,this.wrapS=e.wrapS,this.wrapT=e.wrapT,this.magFilter=e.magFilter,this.minFilter=e.minFilter,this.anisotropy=e.anisotropy,this.format=e.format,this.internalFormat=e.internalFormat,this.type=e.type,this.normalized=e.normalized,this.offset.copy(e.offset),this.repeat.copy(e.repeat),this.center.copy(e.center),this.rotation=e.rotation,this.matrixAutoUpdate=e.matrixAutoUpdate,this.matrix.copy(e.matrix),this.generateMipmaps=e.generateMipmaps,this.premultiplyAlpha=e.premultiplyAlpha,this.flipY=e.flipY,this.unpackAlignment=e.unpackAlignment,this.colorSpace=e.colorSpace,this.renderTarget=e.renderTarget,this.isRenderTargetTexture=e.isRenderTargetTexture,this.isArrayTexture=e.isArrayTexture,this.userData=JSON.parse(JSON.stringify(e.userData)),this.needsUpdate=!0,this}setValues(e){for(let t in e){let n=e[t];if(n===void 0){K(`Texture.setValues(): parameter '${t}' has value of undefined.`);continue}let r=this[t];if(r===void 0){K(`Texture.setValues(): property '${t}' does not exist.`);continue}r&&n&&r.isVector2&&n.isVector2||r&&n&&r.isVector3&&n.isVector3||r&&n&&r.isMatrix3&&n.isMatrix3?r.copy(n):this[t]=n}}toJSON(e){let t=e===void 0||typeof e==`string`;if(!t&&e.textures[this.uuid]!==void 0)return e.textures[this.uuid];let n={metadata:{version:4.7,type:`Texture`,generator:`Texture.toJSON`},uuid:this.uuid,name:this.name,image:this.source.toJSON(e).uuid,mapping:this.mapping,channel:this.channel,repeat:[this.repeat.x,this.repeat.y],offset:[this.offset.x,this.offset.y],center:[this.center.x,this.center.y],rotation:this.rotation,wrap:[this.wrapS,this.wrapT],format:this.format,internalFormat:this.internalFormat,type:this.type,normalized:this.normalized,colorSpace:this.colorSpace,minFilter:this.minFilter,magFilter:this.magFilter,anisotropy:this.anisotropy,flipY:this.flipY,generateMipmaps:this.generateMipmaps,premultiplyAlpha:this.premultiplyAlpha,unpackAlignment:this.unpackAlignment};return Object.keys(this.userData).length>0&&(n.userData=this.userData),t||(e.textures[this.uuid]=n),n}dispose(){this.dispatchEvent({type:`dispose`})}transformUv(e){if(this.mapping!==300)return e;if(e.applyMatrix3(this.matrix),e.x<0||e.x>1)switch(this.wrapS){case Qi:e.x-=Math.floor(e.x);break;case $i:e.x=e.x<0?0:1;break;case ea:Math.abs(Math.floor(e.x)%2)===1?e.x=Math.ceil(e.x)-e.x:e.x-=Math.floor(e.x)}if(e.y<0||e.y>1)switch(this.wrapT){case Qi:e.y-=Math.floor(e.y);break;case $i:e.y=e.y<0?0:1;break;case ea:Math.abs(Math.floor(e.y)%2)===1?e.y=Math.ceil(e.y)-e.y:e.y-=Math.floor(e.y)}return this.flipY&&(e.y=1-e.y),e}set needsUpdate(e){e===!0&&(this.version++,this.source.needsUpdate=!0)}set needsPMREMUpdate(e){e===!0&&this.pmremVersion++}};Os.DEFAULT_IMAGE=null,Os.DEFAULT_MAPPING=300,Os.DEFAULT_ANISOTROPY=1;var ks=class e{static{e.prototype.isVector4=!0}constructor(e=0,t=0,n=0,r=1){this.x=e,this.y=t,this.z=n,this.w=r}get width(){return this.z}set width(e){this.z=e}get height(){return this.w}set height(e){this.w=e}set(e,t,n,r){return this.x=e,this.y=t,this.z=n,this.w=r,this}setScalar(e){return this.x=e,this.y=e,this.z=e,this.w=e,this}setX(e){return this.x=e,this}setY(e){return this.y=e,this}setZ(e){return this.z=e,this}setW(e){return this.w=e,this}setComponent(e,t){switch(e){case 0:this.x=t;break;case 1:this.y=t;break;case 2:this.z=t;break;case 3:this.w=t;break;default:throw Error(`THREE.Vector4: index is out of range: `+e)}return this}getComponent(e){switch(e){case 0:return this.x;case 1:return this.y;case 2:return this.z;case 3:return this.w;default:throw Error(`THREE.Vector4: index is out of range: `+e)}}clone(){return new this.constructor(this.x,this.y,this.z,this.w)}copy(e){return this.x=e.x,this.y=e.y,this.z=e.z,this.w=e.w===void 0?1:e.w,this}add(e){return this.x+=e.x,this.y+=e.y,this.z+=e.z,this.w+=e.w,this}addScalar(e){return this.x+=e,this.y+=e,this.z+=e,this.w+=e,this}addVectors(e,t){return this.x=e.x+t.x,this.y=e.y+t.y,this.z=e.z+t.z,this.w=e.w+t.w,this}addScaledVector(e,t){return this.x+=e.x*t,this.y+=e.y*t,this.z+=e.z*t,this.w+=e.w*t,this}sub(e){return this.x-=e.x,this.y-=e.y,this.z-=e.z,this.w-=e.w,this}subScalar(e){return this.x-=e,this.y-=e,this.z-=e,this.w-=e,this}subVectors(e,t){return this.x=e.x-t.x,this.y=e.y-t.y,this.z=e.z-t.z,this.w=e.w-t.w,this}multiply(e){return this.x*=e.x,this.y*=e.y,this.z*=e.z,this.w*=e.w,this}multiplyScalar(e){return this.x*=e,this.y*=e,this.z*=e,this.w*=e,this}applyMatrix4(e){let t=this.x,n=this.y,r=this.z,i=this.w,a=e.elements;return this.x=a[0]*t+a[4]*n+a[8]*r+a[12]*i,this.y=a[1]*t+a[5]*n+a[9]*r+a[13]*i,this.z=a[2]*t+a[6]*n+a[10]*r+a[14]*i,this.w=a[3]*t+a[7]*n+a[11]*r+a[15]*i,this}divide(e){return this.x/=e.x,this.y/=e.y,this.z/=e.z,this.w/=e.w,this}divideScalar(e){return this.multiplyScalar(1/e)}setAxisAngleFromQuaternion(e){this.w=2*Math.acos(e.w);let t=Math.sqrt(1-e.w*e.w);return t<1e-4?(this.x=1,this.y=0,this.z=0):(this.x=e.x/t,this.y=e.y/t,this.z=e.z/t),this}setAxisAngleFromRotationMatrix(e){let t,n,r,i,a=.01,o=.1,s=e.elements,c=s[0],l=s[4],u=s[8],d=s[1],f=s[5],p=s[9],m=s[2],h=s[6],g=s[10];if(Math.abs(l-d)<a&&Math.abs(u-m)<a&&Math.abs(p-h)<a){if(Math.abs(l+d)<o&&Math.abs(u+m)<o&&Math.abs(p+h)<o&&Math.abs(c+f+g-3)<o)return this.set(1,0,0,0),this;t=Math.PI;let e=(c+1)/2,s=(f+1)/2,_=(g+1)/2,v=(l+d)/4,y=(u+m)/4,b=(p+h)/4;return e>s&&e>_?e<a?(n=0,r=.707106781,i=.707106781):(n=Math.sqrt(e),r=v/n,i=y/n):s>_?s<a?(n=.707106781,r=0,i=.707106781):(r=Math.sqrt(s),n=v/r,i=b/r):_<a?(n=.707106781,r=.707106781,i=0):(i=Math.sqrt(_),n=y/i,r=b/i),this.set(n,r,i,t),this}let _=Math.sqrt((h-p)*(h-p)+(u-m)*(u-m)+(d-l)*(d-l));return Math.abs(_)<.001&&(_=1),this.x=(h-p)/_,this.y=(u-m)/_,this.z=(d-l)/_,this.w=Math.acos((c+f+g-1)/2),this}setFromMatrixPosition(e){let t=e.elements;return this.x=t[12],this.y=t[13],this.z=t[14],this.w=t[15],this}min(e){return this.x=Math.min(this.x,e.x),this.y=Math.min(this.y,e.y),this.z=Math.min(this.z,e.z),this.w=Math.min(this.w,e.w),this}max(e){return this.x=Math.max(this.x,e.x),this.y=Math.max(this.y,e.y),this.z=Math.max(this.z,e.z),this.w=Math.max(this.w,e.w),this}clamp(e,t){return this.x=J(this.x,e.x,t.x),this.y=J(this.y,e.y,t.y),this.z=J(this.z,e.z,t.z),this.w=J(this.w,e.w,t.w),this}clampScalar(e,t){return this.x=J(this.x,e,t),this.y=J(this.y,e,t),this.z=J(this.z,e,t),this.w=J(this.w,e,t),this}clampLength(e,t){let n=this.length();return this.divideScalar(n||1).multiplyScalar(J(n,e,t))}floor(){return this.x=Math.floor(this.x),this.y=Math.floor(this.y),this.z=Math.floor(this.z),this.w=Math.floor(this.w),this}ceil(){return this.x=Math.ceil(this.x),this.y=Math.ceil(this.y),this.z=Math.ceil(this.z),this.w=Math.ceil(this.w),this}round(){return this.x=Math.round(this.x),this.y=Math.round(this.y),this.z=Math.round(this.z),this.w=Math.round(this.w),this}roundToZero(){return this.x=Math.trunc(this.x),this.y=Math.trunc(this.y),this.z=Math.trunc(this.z),this.w=Math.trunc(this.w),this}negate(){return this.x=-this.x,this.y=-this.y,this.z=-this.z,this.w=-this.w,this}dot(e){return this.x*e.x+this.y*e.y+this.z*e.z+this.w*e.w}lengthSq(){return this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w}length(){return Math.sqrt(this.x*this.x+this.y*this.y+this.z*this.z+this.w*this.w)}manhattanLength(){return Math.abs(this.x)+Math.abs(this.y)+Math.abs(this.z)+Math.abs(this.w)}normalize(){return this.divideScalar(this.length()||1)}setLength(e){return this.normalize().multiplyScalar(e)}lerp(e,t){return this.x+=(e.x-this.x)*t,this.y+=(e.y-this.y)*t,this.z+=(e.z-this.z)*t,this.w+=(e.w-this.w)*t,this}lerpVectors(e,t,n){return this.x=e.x+(t.x-e.x)*n,this.y=e.y+(t.y-e.y)*n,this.z=e.z+(t.z-e.z)*n,this.w=e.w+(t.w-e.w)*n,this}equals(e){return e.x===this.x&&e.y===this.y&&e.z===this.z&&e.w===this.w}fromArray(e,t=0){return this.x=e[t],this.y=e[t+1],this.z=e[t+2],this.w=e[t+3],this}toArray(e=[],t=0){return e[t]=this.x,e[t+1]=this.y,e[t+2]=this.z,e[t+3]=this.w,e}fromBufferAttribute(e,t){return this.x=e.getX(t),this.y=e.getY(t),this.z=e.getZ(t),this.w=e.getW(t),this}random(){return this.x=Math.random(),this.y=Math.random(),this.z=Math.random(),this.w=Math.random(),this}*[Symbol.iterator](){yield this.x,yield this.y,yield this.z,yield this.w}},As=class extends Ro{constructor(e=1,t=1,n={}){super(),n=Object.assign({generateMipmaps:!1,internalFormat:null,minFilter:ia,depthBuffer:!0,stencilBuffer:!1,resolveColorBuffer:!0,resolveDepthBuffer:!0,resolveStencilBuffer:!0,storeMultisampledColorBuffer:!0,storeMultisampledDepthBuffer:!0,storeMultisampledStencilBuffer:!0,depthTexture:null,samples:0,count:1,depth:1,multiview:!1,useArrayDepthTexture:!1},n),this.isRenderTarget=!0,this.width=e,this.height=t,this.depth=n.depth,this.scissor=new ks(0,0,e,t),this.scissorTest=!1,this.viewport=new ks(0,0,e,t),this.textures=[];let r=new Os({width:e,height:t,depth:n.depth}),i=n.count;for(let e=0;e<i;e++)this.textures[e]=r.clone(),this.textures[e].isRenderTargetTexture=!0,this.textures[e].renderTarget=this;this._setTextureOptions(n),this.depthBuffer=n.depthBuffer,this.stencilBuffer=n.stencilBuffer,this.resolveColorBuffer=n.resolveColorBuffer,this.resolveDepthBuffer=n.resolveDepthBuffer,this.resolveStencilBuffer=n.resolveStencilBuffer,this.storeMultisampledColorBuffer=n.storeMultisampledColorBuffer,this.storeMultisampledDepthBuffer=n.storeMultisampledDepthBuffer,this.storeMultisampledStencilBuffer=n.storeMultisampledStencilBuffer,this._depthTexture=null,this.depthTexture=n.depthTexture,this.samples=n.samples,this.multiview=n.multiview,this.useArrayDepthTexture=n.useArrayDepthTexture}_setTextureOptions(e={}){let t={minFilter:ia,generateMipmaps:!1,flipY:!1,internalFormat:null};e.mapping!==void 0&&(t.mapping=e.mapping),e.wrapS!==void 0&&(t.wrapS=e.wrapS),e.wrapT!==void 0&&(t.wrapT=e.wrapT),e.wrapR!==void 0&&(t.wrapR=e.wrapR),e.magFilter!==void 0&&(t.magFilter=e.magFilter),e.minFilter!==void 0&&(t.minFilter=e.minFilter),e.format!==void 0&&(t.format=e.format),e.type!==void 0&&(t.type=e.type),e.anisotropy!==void 0&&(t.anisotropy=e.anisotropy),e.colorSpace!==void 0&&(t.colorSpace=e.colorSpace),e.flipY!==void 0&&(t.flipY=e.flipY),e.generateMipmaps!==void 0&&(t.generateMipmaps=e.generateMipmaps),e.internalFormat!==void 0&&(t.internalFormat=e.internalFormat);for(let e=0;e<this.textures.length;e++)this.textures[e].setValues(t)}get texture(){return this.textures[0]}set texture(e){this.textures[0]=e}set depthTexture(e){this._depthTexture!==null&&this._depthTexture.renderTarget===this&&(this._depthTexture.renderTarget=null),e!==null&&e.renderTarget===null&&(e.renderTarget=this),this._depthTexture=e}get depthTexture(){return this._depthTexture}setSize(e,t,n=1){if(this.width!==e||this.height!==t||this.depth!==n){this.width=e,this.height=t,this.depth=n;for(let r=0,i=this.textures.length;r<i;r++)this.textures[r].image.width=e,this.textures[r].image.height=t,this.textures[r].image.depth=n,this.textures[r].isData3DTexture!==!0&&(this.textures[r].isArrayTexture=this.textures[r].image.depth>1);this.dispose()}this.viewport.set(0,0,e,t),this.scissor.set(0,0,e,t)}clone(){return new this.constructor().copy(this)}copy(e){this.width=e.width,this.height=e.height,this.depth=e.depth,this.scissor.copy(e.scissor),this.scissorTest=e.scissorTest,this.viewport.copy(e.viewport),this.textures.length=0;for(let t=0,n=e.textures.length;t<n;t++){this.textures[t]=e.textures[t].clone(),this.textures[t].isRenderTargetTexture=!0,this.textures[t].renderTarget=this;let n=Object.assign({},e.textures[t].image);this.textures[t].source=new ws(n)}if(this.depthBuffer=e.depthBuffer,this.stencilBuffer=e.stencilBuffer,this.resolveColorBuffer=e.resolveColorBuffer,this.resolveDepthBuffer=e.resolveDepthBuffer,this.resolveStencilBuffer=e.resolveStencilBuffer,this.storeMultisampledColorBuffer=e.storeMultisampledColorBuffer,this.storeMultisampledDepthBuffer=e.storeMultisampledDepthBuffer,this.storeMultisampledStencilBuffer=e.storeMultisampledStencilBuffer,e.depthTexture!==null){if(e.depthTexture.renderTarget===e){let t=e.depthTexture.clone();t.renderTarget=null,this.depthTexture=t}else this.depthTexture=e.depthTexture}return this.samples=e.samples,this.multiview=e.multiview,this.useArrayDepthTexture=e.useArrayDepthTexture,this}dispose(){this.dispatchEvent({type:`dispose`})}},js=class extends As{constructor(e=1,t=1,n={}){super(e,t,n),this.isWebGLRenderTarget=!0}},Ms=class extends Os{constructor(e=null,t=1,n=1,r=1){super(null),this.isDataArrayTexture=!0,this.image={data:e,width:t,height:n,depth:r},this.magFilter=ta,this.minFilter=ta,this.wrapR=$i,this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1,this.layerUpdates=new Set}copy(e){return super.copy(e),this.wrapR=e.wrapR,this}addLayerUpdate(e){this.layerUpdates.add(e)}clearLayerUpdates(){this.layerUpdates.clear()}},Ns=class extends Os{constructor(e=null,t=1,n=1,r=1){super(null),this.isData3DTexture=!0,this.image={data:e,width:t,height:n,depth:r},this.magFilter=ta,this.minFilter=ta,this.wrapR=$i,this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1}copy(e){return super.copy(e),this.wrapR=e.wrapR,this}},Ps=class e{static{e.prototype.isMatrix4=!0}constructor(e,t,n,r,i,a,o,s,c,l,u,d,f,p,m,h){this.elements=[1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1],e!==void 0&&this.set(e,t,n,r,i,a,o,s,c,l,u,d,f,p,m,h)}set(e,t,n,r,i,a,o,s,c,l,u,d,f,p,m,h){let g=this.elements;return g[0]=e,g[4]=t,g[8]=n,g[12]=r,g[1]=i,g[5]=a,g[9]=o,g[13]=s,g[2]=c,g[6]=l,g[10]=u,g[14]=d,g[3]=f,g[7]=p,g[11]=m,g[15]=h,this}identity(){return this.set(1,0,0,0,0,1,0,0,0,0,1,0,0,0,0,1),this}clone(){return new e().fromArray(this.elements)}copy(e){let t=this.elements,n=e.elements;return t[0]=n[0],t[1]=n[1],t[2]=n[2],t[3]=n[3],t[4]=n[4],t[5]=n[5],t[6]=n[6],t[7]=n[7],t[8]=n[8],t[9]=n[9],t[10]=n[10],t[11]=n[11],t[12]=n[12],t[13]=n[13],t[14]=n[14],t[15]=n[15],this}copyPosition(e){let t=this.elements,n=e.elements;return t[12]=n[12],t[13]=n[13],t[14]=n[14],this}setFromMatrix3(e){let t=e.elements;return this.set(t[0],t[3],t[6],0,t[1],t[4],t[7],0,t[2],t[5],t[8],0,0,0,0,1),this}extractBasis(e,t,n){return this.determinantAffine()===0?(e.set(1,0,0),t.set(0,1,0),n.set(0,0,1),this):(e.setFromMatrixColumn(this,0),t.setFromMatrixColumn(this,1),n.setFromMatrixColumn(this,2),this)}makeBasis(e,t,n){return this.set(e.x,t.x,n.x,0,e.y,t.y,n.y,0,e.z,t.z,n.z,0,0,0,0,1),this}extractRotation(e){if(e.determinantAffine()===0)return this.identity();let t=this.elements,n=e.elements,r=1/Fs.setFromMatrixColumn(e,0).length(),i=1/Fs.setFromMatrixColumn(e,1).length(),a=1/Fs.setFromMatrixColumn(e,2).length();return t[0]=n[0]*r,t[1]=n[1]*r,t[2]=n[2]*r,t[3]=0,t[4]=n[4]*i,t[5]=n[5]*i,t[6]=n[6]*i,t[7]=0,t[8]=n[8]*a,t[9]=n[9]*a,t[10]=n[10]*a,t[11]=0,t[12]=0,t[13]=0,t[14]=0,t[15]=1,this}makeRotationFromEuler(e){let t=this.elements,n=e.x,r=e.y,i=e.z,a=Math.cos(n),o=Math.sin(n),s=Math.cos(r),c=Math.sin(r),l=Math.cos(i),u=Math.sin(i);if(e.order===`XYZ`){let e=a*l,n=a*u,r=o*l,i=o*u;t[0]=s*l,t[4]=-s*u,t[8]=c,t[1]=n+r*c,t[5]=e-i*c,t[9]=-o*s,t[2]=i-e*c,t[6]=r+n*c,t[10]=a*s}else if(e.order===`YXZ`){let e=s*l,n=s*u,r=c*l,i=c*u;t[0]=e+i*o,t[4]=r*o-n,t[8]=a*c,t[1]=a*u,t[5]=a*l,t[9]=-o,t[2]=n*o-r,t[6]=i+e*o,t[10]=a*s}else if(e.order===`ZXY`){let e=s*l,n=s*u,r=c*l,i=c*u;t[0]=e-i*o,t[4]=-a*u,t[8]=r+n*o,t[1]=n+r*o,t[5]=a*l,t[9]=i-e*o,t[2]=-a*c,t[6]=o,t[10]=a*s}else if(e.order===`ZYX`){let e=a*l,n=a*u,r=o*l,i=o*u;t[0]=s*l,t[4]=r*c-n,t[8]=e*c+i,t[1]=s*u,t[5]=i*c+e,t[9]=n*c-r,t[2]=-c,t[6]=o*s,t[10]=a*s}else if(e.order===`YZX`){let e=a*s,n=a*c,r=o*s,i=o*c;t[0]=s*l,t[4]=i-e*u,t[8]=r*u+n,t[1]=u,t[5]=a*l,t[9]=-o*l,t[2]=-c*l,t[6]=n*u+r,t[10]=e-i*u}else if(e.order===`XZY`){let e=a*s,n=a*c,r=o*s,i=o*c;t[0]=s*l,t[4]=-u,t[8]=c*l,t[1]=e*u+i,t[5]=a*l,t[9]=n*u-r,t[2]=r*u-n,t[6]=o*l,t[10]=i*u+e}return t[3]=0,t[7]=0,t[11]=0,t[12]=0,t[13]=0,t[14]=0,t[15]=1,this}makeRotationFromQuaternion(e){return this.compose(Ls,e,Rs)}lookAt(e,t,n){let r=this.elements;return Vs.subVectors(e,t),Vs.lengthSq()===0&&(Vs.z=1),Vs.normalize(),zs.crossVectors(n,Vs),zs.lengthSq()===0&&(Math.abs(n.z)===1?Vs.x+=1e-4:Vs.z+=1e-4,Vs.normalize(),zs.crossVectors(n,Vs)),zs.normalize(),Bs.crossVectors(Vs,zs),r[0]=zs.x,r[4]=Bs.x,r[8]=Vs.x,r[1]=zs.y,r[5]=Bs.y,r[9]=Vs.y,r[2]=zs.z,r[6]=Bs.z,r[10]=Vs.z,this}multiply(e){return this.multiplyMatrices(this,e)}premultiply(e){return this.multiplyMatrices(e,this)}multiplyMatrices(e,t){let n=e.elements,r=t.elements,i=this.elements,a=n[0],o=n[4],s=n[8],c=n[12],l=n[1],u=n[5],d=n[9],f=n[13],p=n[2],m=n[6],h=n[10],g=n[14],_=n[3],v=n[7],y=n[11],b=n[15],x=r[0],S=r[4],C=r[8],w=r[12],T=r[1],E=r[5],D=r[9],O=r[13],k=r[2],A=r[6],j=r[10],M=r[14],N=r[3],P=r[7],F=r[11],ee=r[15];return i[0]=a*x+o*T+s*k+c*N,i[4]=a*S+o*E+s*A+c*P,i[8]=a*C+o*D+s*j+c*F,i[12]=a*w+o*O+s*M+c*ee,i[1]=l*x+u*T+d*k+f*N,i[5]=l*S+u*E+d*A+f*P,i[9]=l*C+u*D+d*j+f*F,i[13]=l*w+u*O+d*M+f*ee,i[2]=p*x+m*T+h*k+g*N,i[6]=p*S+m*E+h*A+g*P,i[10]=p*C+m*D+h*j+g*F,i[14]=p*w+m*O+h*M+g*ee,i[3]=_*x+v*T+y*k+b*N,i[7]=_*S+v*E+y*A+b*P,i[11]=_*C+v*D+y*j+b*F,i[15]=_*w+v*O+y*M+b*ee,this}multiplyScalar(e){let t=this.elements;return t[0]*=e,t[4]*=e,t[8]*=e,t[12]*=e,t[1]*=e,t[5]*=e,t[9]*=e,t[13]*=e,t[2]*=e,t[6]*=e,t[10]*=e,t[14]*=e,t[3]*=e,t[7]*=e,t[11]*=e,t[15]*=e,this}determinant(){let e=this.elements,t=e[0],n=e[4],r=e[8],i=e[12],a=e[1],o=e[5],s=e[9],c=e[13],l=e[2],u=e[6],d=e[10],f=e[14],p=e[3],m=e[7],h=e[11],g=e[15],_=s*f-c*d,v=o*f-c*u,y=o*d-s*u,b=a*f-c*l,x=a*d-s*l,S=a*u-o*l;return t*(m*_-h*v+g*y)-n*(p*_-h*b+g*x)+r*(p*v-m*b+g*S)-i*(p*y-m*x+h*S)}determinantAffine(){let e=this.elements,t=e[0],n=e[4],r=e[8],i=e[1],a=e[5],o=e[9],s=e[2],c=e[6],l=e[10];return t*(a*l-o*c)-n*(i*l-o*s)+r*(i*c-a*s)}transpose(){let e=this.elements,t;return t=e[1],e[1]=e[4],e[4]=t,t=e[2],e[2]=e[8],e[8]=t,t=e[6],e[6]=e[9],e[9]=t,t=e[3],e[3]=e[12],e[12]=t,t=e[7],e[7]=e[13],e[13]=t,t=e[11],e[11]=e[14],e[14]=t,this}setPosition(e,t,n){let r=this.elements;return e.isVector3?(r[12]=e.x,r[13]=e.y,r[14]=e.z):(r[12]=e,r[13]=t,r[14]=n),this}invert(){let e=this.elements,t=e[0],n=e[1],r=e[2],i=e[3],a=e[4],o=e[5],s=e[6],c=e[7],l=e[8],u=e[9],d=e[10],f=e[11],p=e[12],m=e[13],h=e[14],g=e[15],_=t*o-n*a,v=t*s-r*a,y=t*c-i*a,b=n*s-r*o,x=n*c-i*o,S=r*c-i*s,C=l*m-u*p,w=l*h-d*p,T=l*g-f*p,E=u*h-d*m,D=u*g-f*m,O=d*g-f*h,k=_*O-v*D+y*E+b*T-x*w+S*C;if(k===0)return this.set(0,0,0,0,0,0,0,0,0,0,0,0,0,0,0,0);let A=1/k;return e[0]=(o*O-s*D+c*E)*A,e[1]=(r*D-n*O-i*E)*A,e[2]=(m*S-h*x+g*b)*A,e[3]=(d*x-u*S-f*b)*A,e[4]=(s*T-a*O-c*w)*A,e[5]=(t*O-r*T+i*w)*A,e[6]=(h*y-p*S-g*v)*A,e[7]=(l*S-d*y+f*v)*A,e[8]=(a*D-o*T+c*C)*A,e[9]=(n*T-t*D-i*C)*A,e[10]=(p*x-m*y+g*_)*A,e[11]=(u*y-l*x-f*_)*A,e[12]=(o*w-a*E-s*C)*A,e[13]=(t*E-n*w+r*C)*A,e[14]=(m*v-p*b-h*_)*A,e[15]=(l*b-u*v+d*_)*A,this}scale(e){let t=this.elements,n=e.x,r=e.y,i=e.z;return t[0]*=n,t[4]*=r,t[8]*=i,t[1]*=n,t[5]*=r,t[9]*=i,t[2]*=n,t[6]*=r,t[10]*=i,t[3]*=n,t[7]*=r,t[11]*=i,this}getMaxScaleOnAxis(){let e=this.elements,t=e[0]*e[0]+e[1]*e[1]+e[2]*e[2],n=e[4]*e[4]+e[5]*e[5]+e[6]*e[6],r=e[8]*e[8]+e[9]*e[9]+e[10]*e[10];return Math.sqrt(Math.max(t,n,r))}makeTranslation(e,t,n){return e.isVector3?this.set(1,0,0,e.x,0,1,0,e.y,0,0,1,e.z,0,0,0,1):this.set(1,0,0,e,0,1,0,t,0,0,1,n,0,0,0,1),this}makeRotationX(e){let t=Math.cos(e),n=Math.sin(e);return this.set(1,0,0,0,0,t,-n,0,0,n,t,0,0,0,0,1),this}makeRotationY(e){let t=Math.cos(e),n=Math.sin(e);return this.set(t,0,n,0,0,1,0,0,-n,0,t,0,0,0,0,1),this}makeRotationZ(e){let t=Math.cos(e),n=Math.sin(e);return this.set(t,-n,0,0,n,t,0,0,0,0,1,0,0,0,0,1),this}makeRotationAxis(e,t){let n=Math.cos(t),r=Math.sin(t),i=1-n,a=e.x,o=e.y,s=e.z,c=i*a,l=i*o;return this.set(c*a+n,c*o-r*s,c*s+r*o,0,c*o+r*s,l*o+n,l*s-r*a,0,c*s-r*o,l*s+r*a,i*s*s+n,0,0,0,0,1),this}makeScale(e,t,n){return this.set(e,0,0,0,0,t,0,0,0,0,n,0,0,0,0,1),this}makeShear(e,t,n,r,i,a){return this.set(1,n,i,0,e,1,a,0,t,r,1,0,0,0,0,1),this}compose(e,t,n){let r=this.elements,i=t._x,a=t._y,o=t._z,s=t._w,c=i+i,l=a+a,u=o+o,d=i*c,f=i*l,p=i*u,m=a*l,h=a*u,g=o*u,_=s*c,v=s*l,y=s*u,b=n.x,x=n.y,S=n.z;return r[0]=(1-(m+g))*b,r[1]=(f+y)*b,r[2]=(p-v)*b,r[3]=0,r[4]=(f-y)*x,r[5]=(1-(d+g))*x,r[6]=(h+_)*x,r[7]=0,r[8]=(p+v)*S,r[9]=(h-_)*S,r[10]=(1-(d+m))*S,r[11]=0,r[12]=e.x,r[13]=e.y,r[14]=e.z,r[15]=1,this}decompose(e,t,n){let r=this.elements;e.x=r[12],e.y=r[13],e.z=r[14];let i=this.determinantAffine();if(i===0)return n.set(1,1,1),t.identity(),this;let a=Fs.set(r[0],r[1],r[2]).length(),o=Fs.set(r[4],r[5],r[6]).length(),s=Fs.set(r[8],r[9],r[10]).length();i<0&&(a=-a),Is.copy(this);let c=1/a,l=1/o,u=1/s;return Is.elements[0]*=c,Is.elements[1]*=c,Is.elements[2]*=c,Is.elements[4]*=l,Is.elements[5]*=l,Is.elements[6]*=l,Is.elements[8]*=u,Is.elements[9]*=u,Is.elements[10]*=u,t.setFromRotationMatrix(Is),n.x=a,n.y=o,n.z=s,this}makePerspective(e,t,n,r,i,a,o=Do,s=!1){let c=this.elements,l=2*i/(t-e),u=2*i/(n-r),d=(t+e)/(t-e),f=(n+r)/(n-r),p,m;if(s)p=i/(a-i),m=a*i/(a-i);else if(o===2e3)p=-(a+i)/(a-i),m=-2*a*i/(a-i);else if(o===2001)p=-a/(a-i),m=-a*i/(a-i);else throw Error(`THREE.Matrix4.makePerspective(): Invalid coordinate system: `+o);return c[0]=l,c[4]=0,c[8]=d,c[12]=0,c[1]=0,c[5]=u,c[9]=f,c[13]=0,c[2]=0,c[6]=0,c[10]=p,c[14]=m,c[3]=0,c[7]=0,c[11]=-1,c[15]=0,this}makeOrthographic(e,t,n,r,i,a,o=Do,s=!1){let c=this.elements,l=2/(t-e),u=2/(n-r),d=-(t+e)/(t-e),f=-(n+r)/(n-r),p,m;if(s)p=1/(a-i),m=a/(a-i);else if(o===2e3)p=-2/(a-i),m=-(a+i)/(a-i);else if(o===2001)p=-1/(a-i),m=-i/(a-i);else throw Error(`THREE.Matrix4.makeOrthographic(): Invalid coordinate system: `+o);return c[0]=l,c[4]=0,c[8]=0,c[12]=d,c[1]=0,c[5]=u,c[9]=0,c[13]=f,c[2]=0,c[6]=0,c[10]=p,c[14]=m,c[3]=0,c[7]=0,c[11]=0,c[15]=1,this}equals(e){let t=this.elements,n=e.elements;for(let e=0;e<16;e++)if(t[e]!==n[e])return!1;return!0}fromArray(e,t=0){for(let n=0;n<16;n++)this.elements[n]=e[n+t];return this}toArray(e=[],t=0){let n=this.elements;return e[t]=n[0],e[t+1]=n[1],e[t+2]=n[2],e[t+3]=n[3],e[t+4]=n[4],e[t+5]=n[5],e[t+6]=n[6],e[t+7]=n[7],e[t+8]=n[8],e[t+9]=n[9],e[t+10]=n[10],e[t+11]=n[11],e[t+12]=n[12],e[t+13]=n[13],e[t+14]=n[14],e[t+15]=n[15],e}},Fs=new X,Is=new Ps,Ls=new X(0,0,0),Rs=new X(1,1,1),zs=new X,Bs=new X,Vs=new X,Hs=new Ps,Us=new ds,Ws=class e{constructor(t=0,n=0,r=0,i=e.DEFAULT_ORDER){this.isEuler=!0,this._x=t,this._y=n,this._z=r,this._order=i}get x(){return this._x}set x(e){this._x=e,this._onChangeCallback()}get y(){return this._y}set y(e){this._y=e,this._onChangeCallback()}get z(){return this._z}set z(e){this._z=e,this._onChangeCallback()}get order(){return this._order}set order(e){this._order=e,this._onChangeCallback()}set(e,t,n,r=this._order){return this._x=e,this._y=t,this._z=n,this._order=r,this._onChangeCallback(),this}clone(){return new this.constructor(this._x,this._y,this._z,this._order)}copy(e){return this._x=e._x,this._y=e._y,this._z=e._z,this._order=e._order,this._onChangeCallback(),this}setFromRotationMatrix(e,t=this._order,n=!0){let r=e.elements,i=r[0],a=r[4],o=r[8],s=r[1],c=r[5],l=r[9],u=r[2],d=r[6],f=r[10];switch(t){case`XYZ`:this._y=Math.asin(J(o,-1,1)),Math.abs(o)<.9999999?(this._x=Math.atan2(-l,f),this._z=Math.atan2(-a,i)):(this._x=Math.atan2(d,c),this._z=0);break;case`YXZ`:this._x=Math.asin(-J(l,-1,1)),Math.abs(l)<.9999999?(this._y=Math.atan2(o,f),this._z=Math.atan2(s,c)):(this._y=Math.atan2(-u,i),this._z=0);break;case`ZXY`:this._x=Math.asin(J(d,-1,1)),Math.abs(d)<.9999999?(this._y=Math.atan2(-u,f),this._z=Math.atan2(-a,c)):(this._y=0,this._z=Math.atan2(s,i));break;case`ZYX`:this._y=Math.asin(-J(u,-1,1)),Math.abs(u)<.9999999?(this._x=Math.atan2(d,f),this._z=Math.atan2(s,i)):(this._x=0,this._z=Math.atan2(-a,c));break;case`YZX`:this._z=Math.asin(J(s,-1,1)),Math.abs(s)<.9999999?(this._x=Math.atan2(-l,c),this._y=Math.atan2(-u,i)):(this._x=0,this._y=Math.atan2(o,f));break;case`XZY`:this._z=Math.asin(-J(a,-1,1)),Math.abs(a)<.9999999?(this._x=Math.atan2(d,c),this._y=Math.atan2(o,i)):(this._x=Math.atan2(-l,f),this._y=0);break;default:K(`Euler: .setFromRotationMatrix() encountered an unknown order: `+t)}return this._order=t,n===!0&&this._onChangeCallback(),this}setFromQuaternion(e,t,n){return Hs.makeRotationFromQuaternion(e),this.setFromRotationMatrix(Hs,t,n)}setFromVector3(e,t=this._order){return this.set(e.x,e.y,e.z,t)}reorder(e){return Us.setFromEuler(this),this.setFromQuaternion(Us,e)}equals(e){return e._x===this._x&&e._y===this._y&&e._z===this._z&&e._order===this._order}fromArray(e){return this._x=e[0],this._y=e[1],this._z=e[2],e[3]!==void 0&&(this._order=e[3]),this._onChangeCallback(),this}toArray(e=[],t=0){return e[t]=this._x,e[t+1]=this._y,e[t+2]=this._z,e[t+3]=this._order,e}_onChange(e){return this._onChangeCallback=e,this}_onChangeCallback(){}*[Symbol.iterator](){yield this._x,yield this._y,yield this._z,yield this._order}};Ws.DEFAULT_ORDER=`XYZ`;var Gs=class{constructor(){this.mask=1}set(e){this.mask=(1<<e|0)>>>0}enable(e){this.mask|=1<<e|0}enableAll(){this.mask=-1}toggle(e){this.mask^=1<<e|0}disable(e){this.mask&=~(1<<e|0)}disableAll(){this.mask=0}test(e){return(this.mask&e.mask)!==0}isEnabled(e){return!!(this.mask&(1<<e|0))}},Ks=0,qs=new X,Js=new ds,Ys=new Ps,Xs=new X,Zs=new X,Qs=new X,$s=new ds,ec=new X(1,0,0),tc=new X(0,1,0),nc=new X(0,0,1),rc={type:`added`},ic={type:`removed`},ac={type:`childadded`,child:null},oc={type:`childremoved`,child:null},sc=class e extends Ro{constructor(){super(),this.isObject3D=!0,Object.defineProperty(this,"id",{value:Ks++}),this.uuid=Uo(),this.name=``,this.type=`Object3D`,this.parent=null,this.children=[],this.up=e.DEFAULT_UP.clone();let t=new X,n=new Ws,r=new ds,i=new X(1,1,1);function a(){r.setFromEuler(n,!1)}function o(){n.setFromQuaternion(r,void 0,!1)}n._onChange(a),r._onChange(o),Object.defineProperties(this,{position:{configurable:!0,enumerable:!0,value:t},rotation:{configurable:!0,enumerable:!0,value:n},quaternion:{configurable:!0,enumerable:!0,value:r},scale:{configurable:!0,enumerable:!0,value:i},modelViewMatrix:{value:new Ps},normalMatrix:{value:new Z}}),this.matrix=new Ps,this.matrixWorld=new Ps,this.matrixAutoUpdate=e.DEFAULT_MATRIX_AUTO_UPDATE,this.matrixWorldAutoUpdate=e.DEFAULT_MATRIX_WORLD_AUTO_UPDATE,this.matrixWorldNeedsUpdate=!1,this.layers=new Gs,this.visible=!0,this.castShadow=!1,this.receiveShadow=!1,this.frustumCulled=!0,this.renderOrder=0,this.animations=[],this.customDepthMaterial=void 0,this.customDistanceMaterial=void 0,this.static=!1,this.userData={},this.pivot=null}onBeforeShadow(){}onAfterShadow(){}onBeforeRender(){}onAfterRender(){}applyMatrix4(e){this.matrixAutoUpdate&&this.updateMatrix(),this.matrix.premultiply(e),this.matrix.decompose(this.position,this.quaternion,this.scale)}applyQuaternion(e){return this.quaternion.premultiply(e),this}setRotationFromAxisAngle(e,t){this.quaternion.setFromAxisAngle(e,t)}setRotationFromEuler(e){this.quaternion.setFromEuler(e,!0)}setRotationFromMatrix(e){this.quaternion.setFromRotationMatrix(e)}setRotationFromQuaternion(e){this.quaternion.copy(e)}rotateOnAxis(e,t){return Js.setFromAxisAngle(e,t),this.quaternion.multiply(Js),this}rotateOnWorldAxis(e,t){return Js.setFromAxisAngle(e,t),this.quaternion.premultiply(Js),this}rotateX(e){return this.rotateOnAxis(ec,e)}rotateY(e){return this.rotateOnAxis(tc,e)}rotateZ(e){return this.rotateOnAxis(nc,e)}translateOnAxis(e,t){return qs.copy(e).applyQuaternion(this.quaternion),this.position.add(qs.multiplyScalar(t)),this}translateX(e){return this.translateOnAxis(ec,e)}translateY(e){return this.translateOnAxis(tc,e)}translateZ(e){return this.translateOnAxis(nc,e)}localToWorld(e){return this.updateWorldMatrix(!0,!1),e.applyMatrix4(this.matrixWorld)}worldToLocal(e){return this.updateWorldMatrix(!0,!1),e.applyMatrix4(Ys.copy(this.matrixWorld).invert())}lookAt(e,t,n){e.isVector3?Xs.copy(e):Xs.set(e,t,n);let r=this.parent;this.updateWorldMatrix(!0,!1),Zs.setFromMatrixPosition(this.matrixWorld),this.isCamera||this.isLight?Ys.lookAt(Zs,Xs,this.up):Ys.lookAt(Xs,Zs,this.up),this.quaternion.setFromRotationMatrix(Ys),r&&(Ys.extractRotation(r.matrixWorld),Js.setFromRotationMatrix(Ys),this.quaternion.premultiply(Js.invert()))}add(e){if(arguments.length>1){for(let e=0;e<arguments.length;e++)this.add(arguments[e]);return this}return e===this?(q(`Object3D.add: object can't be added as a child of itself.`,e),this):(e&&e.isObject3D?(e.removeFromParent(),e.parent=this,this.children.push(e),e.dispatchEvent(rc),ac.child=e,this.dispatchEvent(ac),ac.child=null):q(`Object3D.add: object not an instance of THREE.Object3D.`,e),this)}remove(e){if(arguments.length>1){for(let e=0;e<arguments.length;e++)this.remove(arguments[e]);return this}let t=this.children.indexOf(e);return t!==-1&&(e.parent=null,this.children.splice(t,1),e.dispatchEvent(ic),oc.child=e,this.dispatchEvent(oc),oc.child=null),this}removeFromParent(){let e=this.parent;return e!==null&&e.remove(this),this}clear(){return this.remove(...this.children)}attach(e){return this.updateWorldMatrix(!0,!1),Ys.copy(this.matrixWorld).invert(),e.parent!==null&&(e.parent.updateWorldMatrix(!0,!1),Ys.multiply(e.parent.matrixWorld)),e.applyMatrix4(Ys),e.removeFromParent(),e.parent=this,this.children.push(e),e.updateWorldMatrix(!1,!0),e.dispatchEvent(rc),ac.child=e,this.dispatchEvent(ac),ac.child=null,this}getObjectById(e){return this.getObjectByProperty(`id`,e)}getObjectByName(e){return this.getObjectByProperty(`name`,e)}getObjectByProperty(e,t){if(this[e]===t)return this;for(let n=0,r=this.children.length;n<r;n++){let r=this.children[n].getObjectByProperty(e,t);if(r!==void 0)return r}}getObjectsByProperty(e,t,n=[]){this[e]===t&&n.push(this);let r=this.children;for(let i=0,a=r.length;i<a;i++)r[i].getObjectsByProperty(e,t,n);return n}getWorldPosition(e){return this.updateWorldMatrix(!0,!1),e.setFromMatrixPosition(this.matrixWorld)}getWorldQuaternion(e){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(Zs,e,Qs),e}getWorldScale(e){return this.updateWorldMatrix(!0,!1),this.matrixWorld.decompose(Zs,$s,e),e}getWorldDirection(e){this.updateWorldMatrix(!0,!1);let t=this.matrixWorld.elements;return e.set(t[8],t[9],t[10]).normalize()}raycast(){}intersectsFrustum(){}traverse(e){e(this);let t=this.children;for(let n=0,r=t.length;n<r;n++)t[n].traverse(e)}traverseVisible(e){if(this.visible===!1)return;e(this);let t=this.children;for(let n=0,r=t.length;n<r;n++)t[n].traverseVisible(e)}traverseAncestors(e){let t=this.parent;t!==null&&(e(t),t.traverseAncestors(e))}updateMatrix(){this.matrix.compose(this.position,this.quaternion,this.scale);let e=this.pivot;if(e!==null){let t=e.x,n=e.y,r=e.z,i=this.matrix.elements;i[12]+=t-i[0]*t-i[4]*n-i[8]*r,i[13]+=n-i[1]*t-i[5]*n-i[9]*r,i[14]+=r-i[2]*t-i[6]*n-i[10]*r}this.matrixWorldNeedsUpdate=!0}updateMatrixWorld(e){this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||e)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,e=!0);let t=this.children;for(let n=0,r=t.length;n<r;n++)t[n].updateMatrixWorld(e)}updateWorldMatrix(e,t,n=!1){let r=this.parent;if(e===!0&&r!==null&&r.updateWorldMatrix(!0,!1),this.matrixAutoUpdate&&this.updateMatrix(),(this.matrixWorldNeedsUpdate||n)&&(this.matrixWorldAutoUpdate===!0&&(this.parent===null?this.matrixWorld.copy(this.matrix):this.matrixWorld.multiplyMatrices(this.parent.matrixWorld,this.matrix)),this.matrixWorldNeedsUpdate=!1,n=!0),t===!0){let e=this.children;for(let t=0,r=e.length;t<r;t++)e[t].updateWorldMatrix(!1,!0,n)}}toJSON(e){let t=e===void 0||typeof e==`string`,n={};t&&(e={geometries:{},materials:{},textures:{},images:{},shapes:{},skeletons:{},animations:{},nodes:{}},n.metadata={version:4.7,type:`Object`,generator:`Object3D.toJSON`});let r={};r.uuid=this.uuid,r.type=this.type,r.name=this.name,r.castShadow=this.castShadow,r.receiveShadow=this.receiveShadow,r.visible=this.visible,r.frustumCulled=this.frustumCulled,r.renderOrder=this.renderOrder,r.static=this.static,r.matrixAutoUpdate=this.matrixAutoUpdate,Object.keys(this.userData).length>0&&(r.userData=this.userData),r.layers=this.layers.mask,r.matrix=this.matrix.toArray(),r.up=this.up.toArray(),this.pivot!==null&&(r.pivot=this.pivot.toArray()),this.morphTargetDictionary!==void 0&&(r.morphTargetDictionary=Object.assign({},this.morphTargetDictionary)),this.morphTargetInfluences!==void 0&&(r.morphTargetInfluences=this.morphTargetInfluences.slice()),this.isInstancedMesh&&(r.type=`InstancedMesh`,r.count=this.count,r.instanceMatrix=this.instanceMatrix.toJSON(),this.instanceColor!==null&&(r.instanceColor=this.instanceColor.toJSON())),this.isBatchedMesh&&(r.type=`BatchedMesh`,r.perObjectFrustumCulled=this.perObjectFrustumCulled,r.sortObjects=this.sortObjects,r.drawRanges=this._drawRanges,r.reservedRanges=this._reservedRanges,r.geometryInfo=this._geometryInfo.map(e=>({...e,boundingBox:e.boundingBox?e.boundingBox.toJSON():void 0,boundingSphere:e.boundingSphere?e.boundingSphere.toJSON():void 0})),r.instanceInfo=this._instanceInfo.map(e=>({...e})),r.availableInstanceIds=this._availableInstanceIds.slice(),r.availableGeometryIds=this._availableGeometryIds.slice(),r.nextIndexStart=this._nextIndexStart,r.nextVertexStart=this._nextVertexStart,r.geometryCount=this._geometryCount,r.maxInstanceCount=this._maxInstanceCount,r.maxVertexCount=this._maxVertexCount,r.maxIndexCount=this._maxIndexCount,r.geometryInitialized=this._geometryInitialized,r.matricesTexture=this._matricesTexture.toJSON(e),r.indirectTexture=this._indirectTexture.toJSON(e),this._colorsTexture!==null&&(r.colorsTexture=this._colorsTexture.toJSON(e)),this.boundingSphere!==null&&(r.boundingSphere=this.boundingSphere.toJSON()),this.boundingBox!==null&&(r.boundingBox=this.boundingBox.toJSON()));function i(t,n){return t[n.uuid]===void 0&&(t[n.uuid]=n.toJSON(e)),n.uuid}if(this.isScene)this.background&&(this.background.isColor?r.background=this.background.toJSON():this.background.isTexture&&(r.background=this.background.toJSON(e).uuid)),this.environment&&this.environment.isTexture&&this.environment.isRenderTargetTexture!==!0&&(r.environment=this.environment.toJSON(e).uuid);else if(this.isMesh||this.isLine||this.isPoints){r.geometry=i(e.geometries,this.geometry);let t=this.geometry.parameters;if(t!==void 0&&t.shapes!==void 0){let n=t.shapes;if(Array.isArray(n))for(let t=0,r=n.length;t<r;t++){let r=n[t];i(e.shapes,r)}else i(e.shapes,n)}}if(this.isSkinnedMesh&&(r.bindMode=this.bindMode,r.bindMatrix=this.bindMatrix.toArray(),this.skeleton!==void 0&&(i(e.skeletons,this.skeleton),r.skeleton=this.skeleton.uuid)),this.material!==void 0){if(Array.isArray(this.material)){let t=[];for(let n=0,r=this.material.length;n<r;n++)t.push(i(e.materials,this.material[n]));r.material=t}else r.material=i(e.materials,this.material)}if(this.children.length>0){r.children=[];for(let t=0;t<this.children.length;t++)r.children.push(this.children[t].toJSON(e).object)}if(this.animations.length>0){r.animations=[];for(let t=0;t<this.animations.length;t++){let n=this.animations[t];r.animations.push(i(e.animations,n))}}if(t){let t=a(e.geometries),r=a(e.materials),i=a(e.textures),o=a(e.images),s=a(e.shapes),c=a(e.skeletons),l=a(e.animations),u=a(e.nodes);t.length>0&&(n.geometries=t),r.length>0&&(n.materials=r),i.length>0&&(n.textures=i),o.length>0&&(n.images=o),s.length>0&&(n.shapes=s),c.length>0&&(n.skeletons=c),l.length>0&&(n.animations=l),u.length>0&&(n.nodes=u)}return n.object=r,n;function a(e){let t=[];for(let n in e){let r=e[n];delete r.metadata,t.push(r)}return t}}clone(e){return new this.constructor().copy(this,e)}copy(e,t=!0){if(this.name=e.name,this.up.copy(e.up),this.position.copy(e.position),this.rotation.order=e.rotation.order,this.quaternion.copy(e.quaternion),this.scale.copy(e.scale),this.pivot=e.pivot===null?null:e.pivot.clone(),this.matrix.copy(e.matrix),this.matrixWorld.copy(e.matrixWorld),this.matrixAutoUpdate=e.matrixAutoUpdate,this.matrixWorldAutoUpdate=e.matrixWorldAutoUpdate,this.matrixWorldNeedsUpdate=e.matrixWorldNeedsUpdate,this.layers.mask=e.layers.mask,this.visible=e.visible,this.castShadow=e.castShadow,this.receiveShadow=e.receiveShadow,this.frustumCulled=e.frustumCulled,this.renderOrder=e.renderOrder,this.static=e.static,this.animations=e.animations.slice(),this.userData=JSON.parse(JSON.stringify(e.userData)),t===!0)for(let t=0;t<e.children.length;t++){let n=e.children[t];this.add(n.clone())}return this}dispose(){this.dispatchEvent({type:`dispose`})}};sc.DEFAULT_UP=new X(0,1,0),sc.DEFAULT_MATRIX_AUTO_UPDATE=!0,sc.DEFAULT_MATRIX_WORLD_AUTO_UPDATE=!0;var cc=class extends sc{constructor(){super(),this.isGroup=!0,this.type=`Group`}},lc={type:`move`},uc=class{constructor(){this._targetRay=null,this._grip=null,this._hand=null}getHandSpace(){return this._hand===null&&(this._hand=new cc,this._hand.matrixAutoUpdate=!1,this._hand.visible=!1,this._hand.joints={},this._hand.inputState={pinching:!1}),this._hand}getTargetRaySpace(){return this._targetRay===null&&(this._targetRay=new cc,this._targetRay.matrixAutoUpdate=!1,this._targetRay.visible=!1,this._targetRay.hasLinearVelocity=!1,this._targetRay.linearVelocity=new X,this._targetRay.hasAngularVelocity=!1,this._targetRay.angularVelocity=new X),this._targetRay}getGripSpace(){return this._grip===null&&(this._grip=new cc,this._grip.matrixAutoUpdate=!1,this._grip.visible=!1,this._grip.hasLinearVelocity=!1,this._grip.linearVelocity=new X,this._grip.hasAngularVelocity=!1,this._grip.angularVelocity=new X,this._grip.eventsEnabled=!1),this._grip}dispatchEvent(e){return this._targetRay!==null&&this._targetRay.dispatchEvent(e),this._grip!==null&&this._grip.dispatchEvent(e),this._hand!==null&&this._hand.dispatchEvent(e),this}connect(e){if(e&&e.hand){let t=this._hand;if(t)for(let n of e.hand.values())this._getHandJoint(t,n)}return this.dispatchEvent({type:`connected`,data:e}),this}disconnect(e){return this.dispatchEvent({type:`disconnected`,data:e}),this._targetRay!==null&&(this._targetRay.visible=!1),this._grip!==null&&(this._grip.visible=!1),this._hand!==null&&(this._hand.visible=!1),this}update(e,t,n){let r=null,i=null,a=null,o=this._targetRay,s=this._grip,c=this._hand;if(e&&t.session.visibilityState!==`visible-blurred`){if(c&&e.hand){a=!0;for(let r of e.hand.values()){let e=t.getJointPose(r,n),i=this._getHandJoint(c,r);e!==null&&(i.matrix.fromArray(e.transform.matrix),i.matrix.decompose(i.position,i.rotation,i.scale),i.matrixWorldNeedsUpdate=!0,i.jointRadius=e.radius),i.visible=e!==null}let r=c.joints[`index-finger-tip`],i=c.joints[`thumb-tip`],o=r.position.distanceTo(i.position);c.inputState.pinching&&o>.025?(c.inputState.pinching=!1,this.dispatchEvent({type:`pinchend`,handedness:e.handedness,target:this})):!c.inputState.pinching&&o<=.015&&(c.inputState.pinching=!0,this.dispatchEvent({type:`pinchstart`,handedness:e.handedness,target:this}))}else s!==null&&e.gripSpace&&(i=t.getPose(e.gripSpace,n),i!==null&&(s.matrix.fromArray(i.transform.matrix),s.matrix.decompose(s.position,s.rotation,s.scale),s.matrixWorldNeedsUpdate=!0,i.linearVelocity?(s.hasLinearVelocity=!0,s.linearVelocity.copy(i.linearVelocity)):s.hasLinearVelocity=!1,i.angularVelocity?(s.hasAngularVelocity=!0,s.angularVelocity.copy(i.angularVelocity)):s.hasAngularVelocity=!1,s.eventsEnabled&&s.dispatchEvent({type:`gripUpdated`,data:e,target:this})));o!==null&&(r=t.getPose(e.targetRaySpace,n),r===null&&i!==null&&(r=i),r!==null&&(o.matrix.fromArray(r.transform.matrix),o.matrix.decompose(o.position,o.rotation,o.scale),o.matrixWorldNeedsUpdate=!0,r.linearVelocity?(o.hasLinearVelocity=!0,o.linearVelocity.copy(r.linearVelocity)):o.hasLinearVelocity=!1,r.angularVelocity?(o.hasAngularVelocity=!0,o.angularVelocity.copy(r.angularVelocity)):o.hasAngularVelocity=!1,this.dispatchEvent(lc)))}return o!==null&&(o.visible=r!==null),s!==null&&(s.visible=i!==null),c!==null&&(c.visible=a!==null),this}_getHandJoint(e,t){if(e.joints[t.jointName]===void 0){let n=new cc;n.matrixAutoUpdate=!1,n.visible=!1,e.joints[t.jointName]=n,e.add(n)}return e.joints[t.jointName]}},dc={aliceblue:15792383,antiquewhite:16444375,aqua:65535,aquamarine:8388564,azure:15794175,beige:16119260,bisque:16770244,black:0,blanchedalmond:16772045,blue:255,blueviolet:9055202,brown:10824234,burlywood:14596231,cadetblue:6266528,chartreuse:8388352,chocolate:13789470,coral:16744272,cornflowerblue:6591981,cornsilk:16775388,crimson:14423100,cyan:65535,darkblue:139,darkcyan:35723,darkgoldenrod:12092939,darkgray:11119017,darkgreen:25600,darkgrey:11119017,darkkhaki:12433259,darkmagenta:9109643,darkolivegreen:5597999,darkorange:16747520,darkorchid:10040012,darkred:9109504,darksalmon:15308410,darkseagreen:9419919,darkslateblue:4734347,darkslategray:3100495,darkslategrey:3100495,darkturquoise:52945,darkviolet:9699539,deeppink:16716947,deepskyblue:49151,dimgray:6908265,dimgrey:6908265,dodgerblue:2003199,firebrick:11674146,floralwhite:16775920,forestgreen:2263842,fuchsia:16711935,gainsboro:14474460,ghostwhite:16316671,gold:16766720,goldenrod:14329120,gray:8421504,green:32768,greenyellow:11403055,grey:8421504,honeydew:15794160,hotpink:16738740,indianred:13458524,indigo:4915330,ivory:16777200,khaki:15787660,lavender:15132410,lavenderblush:16773365,lawngreen:8190976,lemonchiffon:16775885,lightblue:11393254,lightcoral:15761536,lightcyan:14745599,lightgoldenrodyellow:16448210,lightgray:13882323,lightgreen:9498256,lightgrey:13882323,lightpink:16758465,lightsalmon:16752762,lightseagreen:2142890,lightskyblue:8900346,lightslategray:7833753,lightslategrey:7833753,lightsteelblue:11584734,lightyellow:16777184,lime:65280,limegreen:3329330,linen:16445670,magenta:16711935,maroon:8388608,mediumaquamarine:6737322,mediumblue:205,mediumorchid:12211667,mediumpurple:9662683,mediumseagreen:3978097,mediumslateblue:8087790,mediumspringgreen:64154,mediumturquoise:4772300,mediumvioletred:13047173,midnightblue:1644912,mintcream:16121850,mistyrose:16770273,moccasin:16770229,navajowhite:16768685,navy:128,oldlace:16643558,olive:8421376,olivedrab:7048739,orange:16753920,orangered:16729344,orchid:14315734,palegoldenrod:15657130,palegreen:10025880,paleturquoise:11529966,palevioletred:14381203,papayawhip:16773077,peachpuff:16767673,peru:13468991,pink:16761035,plum:14524637,powderblue:11591910,purple:8388736,rebeccapurple:6697881,red:16711680,rosybrown:12357519,royalblue:4286945,saddlebrown:9127187,salmon:16416882,sandybrown:16032864,seagreen:3050327,seashell:16774638,sienna:10506797,silver:12632256,skyblue:8900331,slateblue:6970061,slategray:7372944,slategrey:7372944,snow:16775930,springgreen:65407,steelblue:4620980,tan:13808780,teal:32896,thistle:14204888,tomato:16737095,turquoise:4251856,violet:15631086,wheat:16113331,white:16777215,whitesmoke:16119285,yellow:16776960,yellowgreen:10145074},Q={h:0,s:0,l:0},fc={h:0,s:0,l:0};function pc(e,t,n){return n<0&&(n+=1),n>1&&--n,n<1/6?e+(t-e)*6*n:n<1/2?t:n<2/3?e+(t-e)*6*(2/3-n):e}var mc=class{constructor(e,t,n){return this.isColor=!0,this.r=1,this.g=1,this.b=1,this.set(e,t,n)}set(e,t,n){if(t===void 0&&n===void 0){let t=e;t&&t.isColor?this.copy(t):typeof t==`number`?this.setHex(t):typeof t==`string`&&this.setStyle(t)}else this.setRGB(e,t,n);return this}setScalar(e){return this.r=e,this.g=e,this.b=e,this}setHex(e,t=xo){return e=Math.floor(e),this.r=(e>>16&255)/255,this.g=(e>>8&255)/255,this.b=(e&255)/255,vs.colorSpaceToWorking(this,t),this}setRGB(e,t,n,r=vs.workingColorSpace){return this.r=e,this.g=t,this.b=n,vs.colorSpaceToWorking(this,r),this}setHSL(e,t,n,r=vs.workingColorSpace){if(e=Wo(e,1),t=J(t,0,1),n=J(n,0,1),t===0)this.r=this.g=this.b=n;else{let r=n<=.5?n*(1+t):n+t-n*t,i=2*n-r;this.r=pc(i,r,e+1/3),this.g=pc(i,r,e),this.b=pc(i,r,e-1/3)}return vs.colorSpaceToWorking(this,r),this}setStyle(e,t=xo){function n(t){t!==void 0&&parseFloat(t)<1&&K(`Color: Alpha component of `+e+` will be ignored.`)}let r;if(r=/^(\w+)\(([^\)]*)\)/.exec(e)){let i,a=r[1],o=r[2];switch(a){case`rgb`:case`rgba`:if(i=/^\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(i[4]),this.setRGB(Math.min(255,parseInt(i[1],10))/255,Math.min(255,parseInt(i[2],10))/255,Math.min(255,parseInt(i[3],10))/255,t);if(i=/^\s*(\d+)\%\s*,\s*(\d+)\%\s*,\s*(\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(i[4]),this.setRGB(Math.min(100,parseInt(i[1],10))/100,Math.min(100,parseInt(i[2],10))/100,Math.min(100,parseInt(i[3],10))/100,t);break;case`hsl`:case`hsla`:if(i=/^\s*(\d*\.?\d+)\s*,\s*(\d*\.?\d+)\%\s*,\s*(\d*\.?\d+)\%\s*(?:,\s*(\d*\.?\d+)\s*)?$/.exec(o))return n(i[4]),this.setHSL(parseFloat(i[1])/360,parseFloat(i[2])/100,parseFloat(i[3])/100,t);break;default:K(`Color: Unknown color model `+e)}}else if(r=/^\#([A-Fa-f\d]+)$/.exec(e)){let n=r[1],i=n.length;if(i===3)return this.setRGB(parseInt(n.charAt(0),16)/15,parseInt(n.charAt(1),16)/15,parseInt(n.charAt(2),16)/15,t);if(i===6)return this.setHex(parseInt(n,16),t);K(`Color: Invalid hex color `+e)}else if(e&&e.length>0)return this.setColorName(e,t);return this}setColorName(e,t=xo){let n=dc[e.toLowerCase()];return n===void 0?K(`Color: Unknown color `+e):this.setHex(n,t),this}clone(){return new this.constructor(this.r,this.g,this.b)}copy(e){return this.r=e.r,this.g=e.g,this.b=e.b,this}copySRGBToLinear(e){return this.r=ys(e.r),this.g=ys(e.g),this.b=ys(e.b),this}copyLinearToSRGB(e){return this.r=bs(e.r),this.g=bs(e.g),this.b=bs(e.b),this}convertSRGBToLinear(){return this.copySRGBToLinear(this),this}convertLinearToSRGB(){return this.copyLinearToSRGB(this),this}getHex(e=xo){return vs.workingToColorSpace(hc.copy(this),e),Math.round(J(hc.r*255,0,255))*65536+Math.round(J(hc.g*255,0,255))*256+Math.round(J(hc.b*255,0,255))}getHexString(e=xo){return(`000000`+this.getHex(e).toString(16)).slice(-6)}getHSL(e,t=vs.workingColorSpace){vs.workingToColorSpace(hc.copy(this),t);let n=hc.r,r=hc.g,i=hc.b,a=Math.max(n,r,i),o=Math.min(n,r,i),s,c,l=(o+a)/2;if(o===a)s=0,c=0;else{let e=a-o;switch(c=l<=.5?e/(a+o):e/(2-a-o),a){case n:s=(r-i)/e+(r<i?6:0);break;case r:s=(i-n)/e+2;break;case i:s=(n-r)/e+4}s/=6}return e.h=s,e.s=c,e.l=l,e}getRGB(e,t=vs.workingColorSpace){return vs.workingToColorSpace(hc.copy(this),t),e.r=hc.r,e.g=hc.g,e.b=hc.b,e}getStyle(e=xo){vs.workingToColorSpace(hc.copy(this),e);let t=hc.r,n=hc.g,r=hc.b;return e===`srgb`?`rgb(${Math.round(t*255)},${Math.round(n*255)},${Math.round(r*255)})`:`color(${e} ${t.toFixed(3)} ${n.toFixed(3)} ${r.toFixed(3)})`}offsetHSL(e,t,n){return this.getHSL(Q),this.setHSL(Q.h+e,Q.s+t,Q.l+n)}add(e){return this.r+=e.r,this.g+=e.g,this.b+=e.b,this}addColors(e,t){return this.r=e.r+t.r,this.g=e.g+t.g,this.b=e.b+t.b,this}addScalar(e){return this.r+=e,this.g+=e,this.b+=e,this}sub(e){return this.r=Math.max(0,this.r-e.r),this.g=Math.max(0,this.g-e.g),this.b=Math.max(0,this.b-e.b),this}multiply(e){return this.r*=e.r,this.g*=e.g,this.b*=e.b,this}multiplyScalar(e){return this.r*=e,this.g*=e,this.b*=e,this}lerp(e,t){return this.r+=(e.r-this.r)*t,this.g+=(e.g-this.g)*t,this.b+=(e.b-this.b)*t,this}lerpColors(e,t,n){return this.r=e.r+(t.r-e.r)*n,this.g=e.g+(t.g-e.g)*n,this.b=e.b+(t.b-e.b)*n,this}lerpHSL(e,t){this.getHSL(Q),e.getHSL(fc);let n=qo(Q.h,fc.h,t),r=qo(Q.s,fc.s,t),i=qo(Q.l,fc.l,t);return this.setHSL(n,r,i),this}setFromVector3(e){return this.r=e.x,this.g=e.y,this.b=e.z,this}applyMatrix3(e){let t=this.r,n=this.g,r=this.b,i=e.elements;return this.r=i[0]*t+i[3]*n+i[6]*r,this.g=i[1]*t+i[4]*n+i[7]*r,this.b=i[2]*t+i[5]*n+i[8]*r,this}equals(e){return e.r===this.r&&e.g===this.g&&e.b===this.b}fromArray(e,t=0){return this.r=e[t],this.g=e[t+1],this.b=e[t+2],this}toArray(e=[],t=0){return e[t]=this.r,e[t+1]=this.g,e[t+2]=this.b,e}fromBufferAttribute(e,t){return this.r=e.getX(t),this.g=e.getY(t),this.b=e.getZ(t),this}toJSON(){return this.getHex()}*[Symbol.iterator](){yield this.r,yield this.g,yield this.b}},hc=new mc;mc.NAMES=dc;var gc=class extends sc{constructor(){super(),this.isScene=!0,this.type=`Scene`,this.background=null,this.environment=null,this.fog=null,this.backgroundBlurriness=0,this.backgroundIntensity=1,this.backgroundRotation=new Ws,this.environmentIntensity=1,this.environmentRotation=new Ws,this.overrideMaterial=null,typeof __THREE_DEVTOOLS__<`u`&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent(`observe`,{detail:this}))}copy(e,t){return super.copy(e,t),e.background!==null&&(this.background=e.background.clone()),e.environment!==null&&(this.environment=e.environment.clone()),e.fog!==null&&(this.fog=e.fog.clone()),this.backgroundBlurriness=e.backgroundBlurriness,this.backgroundIntensity=e.backgroundIntensity,this.backgroundRotation.copy(e.backgroundRotation),this.environmentIntensity=e.environmentIntensity,this.environmentRotation.copy(e.environmentRotation),e.overrideMaterial!==null&&(this.overrideMaterial=e.overrideMaterial.clone()),this.matrixAutoUpdate=e.matrixAutoUpdate,this}toJSON(e){let t=super.toJSON(e);return this.fog!==null&&(t.object.fog=this.fog.toJSON()),t.object.backgroundBlurriness=this.backgroundBlurriness,t.object.backgroundIntensity=this.backgroundIntensity,t.object.backgroundRotation=this.backgroundRotation.toArray(),t.object.environmentIntensity=this.environmentIntensity,t.object.environmentRotation=this.environmentRotation.toArray(),t}},_c=new X,vc=new X,yc=new X,bc=new X,xc=new X,Sc=new X,Cc=new X,wc=new X,Tc=new X,Ec=new X,Dc=new ks,Oc=new ks,kc=new ks,Ac=class e{constructor(e=new X,t=new X,n=new X){this.a=e,this.b=t,this.c=n}static getNormal(e,t,n,r){r.subVectors(n,t),_c.subVectors(e,t),r.cross(_c);let i=r.lengthSq();return i>0?r.multiplyScalar(1/Math.sqrt(i)):r.set(0,0,0)}static getBarycoord(e,t,n,r,i){_c.subVectors(r,t),vc.subVectors(n,t),yc.subVectors(e,t);let a=_c.dot(_c),o=_c.dot(vc),s=_c.dot(yc),c=vc.dot(vc),l=vc.dot(yc),u=a*c-o*o;if(u===0)return i.set(0,0,0),null;let d=1/u,f=(c*s-o*l)*d,p=(a*l-o*s)*d;return i.set(1-f-p,p,f)}static containsPoint(e,t,n,r){return this.getBarycoord(e,t,n,r,bc)!==null&&bc.x>=0&&bc.y>=0&&bc.x+bc.y<=1}static getInterpolation(e,t,n,r,i,a,o,s){return this.getBarycoord(e,t,n,r,bc)===null?(s.x=0,s.y=0,`z`in s&&(s.z=0),`w`in s&&(s.w=0),null):(s.setScalar(0),s.addScaledVector(i,bc.x),s.addScaledVector(a,bc.y),s.addScaledVector(o,bc.z),s)}static getInterpolatedAttribute(e,t,n,r,i,a){return Dc.setScalar(0),Oc.setScalar(0),kc.setScalar(0),Dc.fromBufferAttribute(e,t),Oc.fromBufferAttribute(e,n),kc.fromBufferAttribute(e,r),a.setScalar(0),a.addScaledVector(Dc,i.x),a.addScaledVector(Oc,i.y),a.addScaledVector(kc,i.z),a}static isFrontFacing(e,t,n,r){return _c.subVectors(n,t),vc.subVectors(e,t),_c.cross(vc).dot(r)<0}set(e,t,n){return this.a.copy(e),this.b.copy(t),this.c.copy(n),this}setFromPointsAndIndices(e,t,n,r){return this.a.copy(e[t]),this.b.copy(e[n]),this.c.copy(e[r]),this}setFromAttributeAndIndices(e,t,n,r){return this.a.fromBufferAttribute(e,t),this.b.fromBufferAttribute(e,n),this.c.fromBufferAttribute(e,r),this}clone(){return new this.constructor().copy(this)}copy(e){return this.a.copy(e.a),this.b.copy(e.b),this.c.copy(e.c),this}getArea(){return _c.subVectors(this.c,this.b),vc.subVectors(this.a,this.b),_c.cross(vc).length()*.5}getMidpoint(e){return e.addVectors(this.a,this.b).add(this.c).multiplyScalar(1/3)}getNormal(t){return e.getNormal(this.a,this.b,this.c,t)}getPlane(e){return e.setFromCoplanarPoints(this.a,this.b,this.c)}getBarycoord(t,n){return e.getBarycoord(t,this.a,this.b,this.c,n)}getInterpolation(t,n,r,i,a){return e.getInterpolation(t,this.a,this.b,this.c,n,r,i,a)}containsPoint(t){return e.containsPoint(t,this.a,this.b,this.c)}isFrontFacing(t){return e.isFrontFacing(this.a,this.b,this.c,t)}intersectsBox(e){return e.intersectsTriangle(this)}closestPointToPoint(e,t){let n=this.a,r=this.b,i=this.c,a,o;xc.subVectors(r,n),Sc.subVectors(i,n),wc.subVectors(e,n);let s=xc.dot(wc),c=Sc.dot(wc);if(s<=0&&c<=0)return t.copy(n);Tc.subVectors(e,r);let l=xc.dot(Tc),u=Sc.dot(Tc);if(l>=0&&u<=l)return t.copy(r);let d=s*u-l*c;if(d<=0&&s>=0&&l<=0)return a=s/(s-l),t.copy(n).addScaledVector(xc,a);Ec.subVectors(e,i);let f=xc.dot(Ec),p=Sc.dot(Ec);if(p>=0&&f<=p)return t.copy(i);let m=f*c-s*p;if(m<=0&&c>=0&&p<=0)return o=c/(c-p),t.copy(n).addScaledVector(Sc,o);let h=l*p-f*u;if(h<=0&&u-l>=0&&f-p>=0)return Cc.subVectors(i,r),o=(u-l)/(u-l+(f-p)),t.copy(r).addScaledVector(Cc,o);let g=1/(h+m+d);return a=m*g,o=d*g,t.copy(n).addScaledVector(xc,a).addScaledVector(Sc,o)}equals(e){return e.a.equals(this.a)&&e.b.equals(this.b)&&e.c.equals(this.c)}},jc=class{constructor(e=new X(1/0,1/0,1/0),t=new X(-1/0,-1/0,-1/0)){this.isBox3=!0,this.min=e,this.max=t}set(e,t){return this.min.copy(e),this.max.copy(t),this}setFromArray(e){this.makeEmpty();for(let t=0,n=e.length;t<n;t+=3)this.expandByPoint(Nc.fromArray(e,t));return this}setFromBufferAttribute(e){this.makeEmpty();for(let t=0,n=e.count;t<n;t++)this.expandByPoint(Nc.fromBufferAttribute(e,t));return this}setFromPoints(e){this.makeEmpty();for(let t=0,n=e.length;t<n;t++)this.expandByPoint(e[t]);return this}setFromCenterAndSize(e,t){let n=Nc.copy(t).multiplyScalar(.5);return this.min.copy(e).sub(n),this.max.copy(e).add(n),this}setFromObject(e,t=!1){return this.makeEmpty(),this.expandByObject(e,t)}clone(){return new this.constructor().copy(this)}copy(e){return this.min.copy(e.min),this.max.copy(e.max),this}makeEmpty(){return this.min.x=this.min.y=this.min.z=1/0,this.max.x=this.max.y=this.max.z=-1/0,this}isEmpty(){return this.max.x<this.min.x||this.max.y<this.min.y||this.max.z<this.min.z}getCenter(e){return this.isEmpty()?e.set(0,0,0):e.addVectors(this.min,this.max).multiplyScalar(.5)}getSize(e){return this.isEmpty()?e.set(0,0,0):e.subVectors(this.max,this.min)}expandByPoint(e){return this.min.min(e),this.max.max(e),this}expandByVector(e){return this.min.sub(e),this.max.add(e),this}expandByScalar(e){return this.min.addScalar(-e),this.max.addScalar(e),this}expandByObject(e,t=!1){e.updateWorldMatrix(!1,!1);let n=e.geometry;if(n!==void 0){let r=n.getAttribute(`position`);if(t===!0&&r!==void 0&&e.isInstancedMesh!==!0)for(let t=0,n=r.count;t<n;t++)e.isMesh===!0?e.getVertexPosition(t,Nc):Nc.fromBufferAttribute(r,t),Nc.applyMatrix4(e.matrixWorld),this.expandByPoint(Nc);else e.boundingBox===void 0?(n.boundingBox===null&&n.computeBoundingBox(),Pc.copy(n.boundingBox)):(e.boundingBox===null&&e.computeBoundingBox(),Pc.copy(e.boundingBox)),Pc.applyMatrix4(e.matrixWorld),this.union(Pc)}let r=e.children;for(let e=0,n=r.length;e<n;e++)this.expandByObject(r[e],t);return this}containsPoint(e){return e.x>=this.min.x&&e.x<=this.max.x&&e.y>=this.min.y&&e.y<=this.max.y&&e.z>=this.min.z&&e.z<=this.max.z}containsBox(e){return this.min.x<=e.min.x&&e.max.x<=this.max.x&&this.min.y<=e.min.y&&e.max.y<=this.max.y&&this.min.z<=e.min.z&&e.max.z<=this.max.z}getParameter(e,t){return t.set((e.x-this.min.x)/(this.max.x-this.min.x),(e.y-this.min.y)/(this.max.y-this.min.y),(e.z-this.min.z)/(this.max.z-this.min.z))}intersectsBox(e){return e.max.x>=this.min.x&&e.min.x<=this.max.x&&e.max.y>=this.min.y&&e.min.y<=this.max.y&&e.max.z>=this.min.z&&e.min.z<=this.max.z}intersectsSphere(e){return this.clampPoint(e.center,Nc),Nc.distanceToSquared(e.center)<=e.radius*e.radius}intersectsPlane(e){let t,n;return e.normal.x>0?(t=e.normal.x*this.min.x,n=e.normal.x*this.max.x):(t=e.normal.x*this.max.x,n=e.normal.x*this.min.x),e.normal.y>0?(t+=e.normal.y*this.min.y,n+=e.normal.y*this.max.y):(t+=e.normal.y*this.max.y,n+=e.normal.y*this.min.y),e.normal.z>0?(t+=e.normal.z*this.min.z,n+=e.normal.z*this.max.z):(t+=e.normal.z*this.max.z,n+=e.normal.z*this.min.z),t<=-e.constant&&n>=-e.constant}intersectsTriangle(e){if(this.isEmpty())return!1;this.getCenter(Vc),Hc.subVectors(this.max,Vc),Fc.subVectors(e.a,Vc),Ic.subVectors(e.b,Vc),Lc.subVectors(e.c,Vc),Rc.subVectors(Ic,Fc),zc.subVectors(Lc,Ic),Bc.subVectors(Fc,Lc);let t=[0,-Rc.z,Rc.y,0,-zc.z,zc.y,0,-Bc.z,Bc.y,Rc.z,0,-Rc.x,zc.z,0,-zc.x,Bc.z,0,-Bc.x,-Rc.y,Rc.x,0,-zc.y,zc.x,0,-Bc.y,Bc.x,0];return!Gc(t,Fc,Ic,Lc,Hc)||(t=[1,0,0,0,1,0,0,0,1],!Gc(t,Fc,Ic,Lc,Hc))?!1:(Uc.crossVectors(Rc,zc),t=[Uc.x,Uc.y,Uc.z],Gc(t,Fc,Ic,Lc,Hc))}clampPoint(e,t){return t.copy(e).clamp(this.min,this.max)}distanceToPoint(e){return this.clampPoint(e,Nc).distanceTo(e)}getBoundingSphere(e){return this.isEmpty()?e.makeEmpty():(this.getCenter(e.center),e.radius=this.getSize(Nc).length()*.5),e}intersect(e){return this.min.max(e.min),this.max.min(e.max),this.isEmpty()&&this.makeEmpty(),this}union(e){return this.min.min(e.min),this.max.max(e.max),this}applyMatrix4(e){return this.isEmpty()?this:(Mc[0].set(this.min.x,this.min.y,this.min.z).applyMatrix4(e),Mc[1].set(this.min.x,this.min.y,this.max.z).applyMatrix4(e),Mc[2].set(this.min.x,this.max.y,this.min.z).applyMatrix4(e),Mc[3].set(this.min.x,this.max.y,this.max.z).applyMatrix4(e),Mc[4].set(this.max.x,this.min.y,this.min.z).applyMatrix4(e),Mc[5].set(this.max.x,this.min.y,this.max.z).applyMatrix4(e),Mc[6].set(this.max.x,this.max.y,this.min.z).applyMatrix4(e),Mc[7].set(this.max.x,this.max.y,this.max.z).applyMatrix4(e),this.setFromPoints(Mc),this)}translate(e){return this.min.add(e),this.max.add(e),this}equals(e){return e.min.equals(this.min)&&e.max.equals(this.max)}toJSON(){return{min:this.min.toArray(),max:this.max.toArray()}}fromJSON(e){return this.min.fromArray(e.min),this.max.fromArray(e.max),this}},Mc=[new X,new X,new X,new X,new X,new X,new X,new X],Nc=new X,Pc=new jc,Fc=new X,Ic=new X,Lc=new X,Rc=new X,zc=new X,Bc=new X,Vc=new X,Hc=new X,Uc=new X,Wc=new X;function Gc(e,t,n,r,i){for(let a=0,o=e.length-3;a<=o;a+=3){Wc.fromArray(e,a);let o=i.x*Math.abs(Wc.x)+i.y*Math.abs(Wc.y)+i.z*Math.abs(Wc.z),s=t.dot(Wc),c=n.dot(Wc),l=r.dot(Wc);if(Math.max(-Math.max(s,c,l),Math.min(s,c,l))>o)return!1}return!0}var Kc=new X,qc=new Y,Jc=0,Yc=class extends Ro{constructor(e,t,n=!1){if(super(),Array.isArray(e))throw TypeError(`THREE.BufferAttribute: array should be a Typed Array.`);this.isBufferAttribute=!0,Object.defineProperty(this,"id",{value:Jc++}),this.name=``,this.array=e,this.itemSize=t,this.count=e===void 0?0:e.length/t,this.normalized=n,this.usage=Eo,this.updateRanges=[],this.gpuType=pa,this.version=0}onUploadCallback(){}set needsUpdate(e){e===!0&&this.version++}setUsage(e){return this.usage=e,this}addUpdateRange(e,t){this.updateRanges.push({start:e,count:t})}clearUpdateRanges(){this.updateRanges.length=0}copy(e){return this.name=e.name,this.array=new e.array.constructor(e.array),this.itemSize=e.itemSize,this.count=e.count,this.normalized=e.normalized,this.usage=e.usage,this.gpuType=e.gpuType,this}copyAt(e,t,n){e*=this.itemSize,n*=t.itemSize;for(let r=0,i=this.itemSize;r<i;r++)this.array[e+r]=t.array[n+r];return this}copyArray(e){return this.array.set(e),this}applyMatrix3(e){if(this.itemSize===2)for(let t=0,n=this.count;t<n;t++)qc.fromBufferAttribute(this,t),qc.applyMatrix3(e),this.setXY(t,qc.x,qc.y);else if(this.itemSize===3)for(let t=0,n=this.count;t<n;t++)Kc.fromBufferAttribute(this,t),Kc.applyMatrix3(e),this.setXYZ(t,Kc.x,Kc.y,Kc.z);return this}applyMatrix4(e){for(let t=0,n=this.count;t<n;t++)Kc.fromBufferAttribute(this,t),Kc.applyMatrix4(e),this.setXYZ(t,Kc.x,Kc.y,Kc.z);return this}applyNormalMatrix(e){for(let t=0,n=this.count;t<n;t++)Kc.fromBufferAttribute(this,t),Kc.applyNormalMatrix(e),this.setXYZ(t,Kc.x,Kc.y,Kc.z);return this}transformDirection(e){for(let t=0,n=this.count;t<n;t++)Kc.fromBufferAttribute(this,t),Kc.transformDirection(e),this.setXYZ(t,Kc.x,Kc.y,Kc.z);return this}set(e,t=0){return this.array.set(e,t),this}getComponent(e,t){let n=this.array[e*this.itemSize+t];return this.normalized&&(n=cs(n,this.array)),n}setComponent(e,t,n){return this.normalized&&(n=ls(n,this.array)),this.array[e*this.itemSize+t]=n,this}getX(e){let t=this.array[e*this.itemSize];return this.normalized&&(t=cs(t,this.array)),t}setX(e,t){return this.normalized&&(t=ls(t,this.array)),this.array[e*this.itemSize]=t,this}getY(e){let t=this.array[e*this.itemSize+1];return this.normalized&&(t=cs(t,this.array)),t}setY(e,t){return this.normalized&&(t=ls(t,this.array)),this.array[e*this.itemSize+1]=t,this}getZ(e){let t=this.array[e*this.itemSize+2];return this.normalized&&(t=cs(t,this.array)),t}setZ(e,t){return this.normalized&&(t=ls(t,this.array)),this.array[e*this.itemSize+2]=t,this}getW(e){let t=this.array[e*this.itemSize+3];return this.normalized&&(t=cs(t,this.array)),t}setW(e,t){return this.normalized&&(t=ls(t,this.array)),this.array[e*this.itemSize+3]=t,this}setXY(e,t,n){return e*=this.itemSize,this.normalized&&(t=ls(t,this.array),n=ls(n,this.array)),this.array[e+0]=t,this.array[e+1]=n,this}setXYZ(e,t,n,r){return e*=this.itemSize,this.normalized&&(t=ls(t,this.array),n=ls(n,this.array),r=ls(r,this.array)),this.array[e+0]=t,this.array[e+1]=n,this.array[e+2]=r,this}setXYZW(e,t,n,r,i){return e*=this.itemSize,this.normalized&&(t=ls(t,this.array),n=ls(n,this.array),r=ls(r,this.array),i=ls(i,this.array)),this.array[e+0]=t,this.array[e+1]=n,this.array[e+2]=r,this.array[e+3]=i,this}onUpload(e){return this.onUploadCallback=e,this}clone(){return new this.constructor(this.array,this.itemSize).copy(this)}toJSON(){let e={itemSize:this.itemSize,type:this.array.constructor.name,array:Array.from(this.array),normalized:this.normalized};return e.name=this.name,e.usage=this.usage,e.gpuType=this.gpuType,e}dispose(){this.dispatchEvent({type:`dispose`})}},Xc=class extends Yc{constructor(e,t,n){super(new Uint16Array(e),t,n)}},Zc=class extends Yc{constructor(e,t,n){super(new Uint32Array(e),t,n)}},Qc=class extends Yc{constructor(e,t,n){super(new Float32Array(e),t,n)}},$c=new jc,el=new X,tl=new X,nl=class{constructor(e=new X,t=-1){this.isSphere=!0,this.center=e,this.radius=t}set(e,t){return this.center.copy(e),this.radius=t,this}setFromPoints(e,t){let n=this.center;t===void 0?$c.setFromPoints(e).getCenter(n):n.copy(t);let r=0;for(let t=0,i=e.length;t<i;t++)r=Math.max(r,n.distanceToSquared(e[t]));return this.radius=Math.sqrt(r),this}copy(e){return this.center.copy(e.center),this.radius=e.radius,this}isEmpty(){return this.radius<0}makeEmpty(){return this.center.set(0,0,0),this.radius=-1,this}containsPoint(e){return e.distanceToSquared(this.center)<=this.radius*this.radius}distanceToPoint(e){return e.distanceTo(this.center)-this.radius}intersectsSphere(e){let t=this.radius+e.radius;return e.center.distanceToSquared(this.center)<=t*t}intersectsBox(e){return e.intersectsSphere(this)}intersectsPlane(e){return Math.abs(e.distanceToPoint(this.center))<=this.radius}clampPoint(e,t){let n=this.center.distanceToSquared(e);return t.copy(e),n>this.radius*this.radius&&(t.sub(this.center).normalize(),t.multiplyScalar(this.radius).add(this.center)),t}getBoundingBox(e){return this.isEmpty()?(e.makeEmpty(),e):(e.set(this.center,this.center),e.expandByScalar(this.radius),e)}applyMatrix4(e){return this.center.applyMatrix4(e),this.radius*=e.getMaxScaleOnAxis(),this}translate(e){return this.center.add(e),this}expandByPoint(e){if(this.isEmpty())return this.center.copy(e),this.radius=0,this;el.subVectors(e,this.center);let t=el.lengthSq();if(t>this.radius*this.radius){let e=Math.sqrt(t),n=(e-this.radius)*.5;this.center.addScaledVector(el,n/e),this.radius+=n}return this}union(e){return e.isEmpty()?this:this.isEmpty()?(this.copy(e),this):(this.center.equals(e.center)===!0?this.radius=Math.max(this.radius,e.radius):(tl.subVectors(e.center,this.center).setLength(e.radius),this.expandByPoint(el.copy(e.center).add(tl)),this.expandByPoint(el.copy(e.center).sub(tl))),this)}equals(e){return e.center.equals(this.center)&&e.radius===this.radius}clone(){return new this.constructor().copy(this)}toJSON(){return{radius:this.radius,center:this.center.toArray()}}fromJSON(e){return this.radius=e.radius,this.center.fromArray(e.center),this}},rl=0,il=new Ps,al=new sc,ol=new X,sl=new jc,cl=new jc,ll=new X,ul=class e extends Ro{constructor(){super(),this.isBufferGeometry=!0,Object.defineProperty(this,"id",{value:rl++}),this.uuid=Uo(),this.name=``,this.type=`BufferGeometry`,this.index=null,this.indirect=null,this.indirectOffset=0,this.attributes={},this.morphAttributes={},this.morphTargetsRelative=!1,this.groups=[],this.boundingBox=null,this.boundingSphere=null,this.drawRange={start:0,count:1/0},this.userData={},this._transformed=!1}getIndex(){return this.index}setIndex(e){return this.index=Array.isArray(e)?new(Oo(e)?Zc:Xc)(e,1):e,this}setIndirect(e,t=0){return this.indirect=e,this.indirectOffset=t,this}getIndirect(){return this.indirect}getAttribute(e){return this.attributes[e]}setAttribute(e,t){return this.attributes[e]=t,this}deleteAttribute(e){return delete this.attributes[e],this}hasAttribute(e){return this.attributes[e]!==void 0}addGroup(e,t,n=0){this.groups.push({start:e,count:t,materialIndex:n})}clearGroups(){this.groups=[]}setDrawRange(e,t){this.drawRange.start=e,this.drawRange.count=t}applyMatrix4(e){let t=this.attributes.position;t!==void 0&&(t.applyMatrix4(e),t.needsUpdate=!0);let n=this.attributes.normal;if(n!==void 0){let t=new Z().getNormalMatrix(e);n.applyNormalMatrix(t),n.needsUpdate=!0}let r=this.attributes.tangent;return r!==void 0&&(r.transformDirection(e),r.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this._transformed=!0,this}applyQuaternion(e){return il.makeRotationFromQuaternion(e),this.applyMatrix4(il),this}rotateX(e){return il.makeRotationX(e),this.applyMatrix4(il),this}rotateY(e){return il.makeRotationY(e),this.applyMatrix4(il),this}rotateZ(e){return il.makeRotationZ(e),this.applyMatrix4(il),this}translate(e,t,n){return il.makeTranslation(e,t,n),this.applyMatrix4(il),this}scale(e,t,n){return il.makeScale(e,t,n),this.applyMatrix4(il),this}lookAt(e){return al.lookAt(e),al.updateMatrix(),this.applyMatrix4(al.matrix),this}center(){return this.computeBoundingBox(),this.boundingBox.getCenter(ol).negate(),this.translate(ol.x,ol.y,ol.z),this}setFromPoints(e){let t=this.getAttribute(`position`);if(t===void 0){let t=[];for(let n=0,r=e.length;n<r;n++){let r=e[n];t.push(r.x,r.y,r.z||0)}this.setAttribute(`position`,new Qc(t,3))}else{let n=Math.min(e.length,t.count);for(let r=0;r<n;r++){let n=e[r];t.setXYZ(r,n.x,n.y,n.z||0)}e.length>t.count&&K(`BufferGeometry: Buffer size too small for points data. Use .dispose() and create a new geometry.`),t.needsUpdate=!0}return this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new jc);let e=this.attributes.position,t=this.morphAttributes.position;if(e&&e.isGLBufferAttribute){q(`BufferGeometry.computeBoundingBox(): GLBufferAttribute requires a manual bounding box.`,this),this.boundingBox.set(new X(-1/0,-1/0,-1/0),new X(1/0,1/0,1/0));return}if(e!==void 0){if(this.boundingBox.setFromBufferAttribute(e),t)for(let e=0,n=t.length;e<n;e++){let n=t[e];sl.setFromBufferAttribute(n),this.morphTargetsRelative?(ll.addVectors(this.boundingBox.min,sl.min),this.boundingBox.expandByPoint(ll),ll.addVectors(this.boundingBox.max,sl.max),this.boundingBox.expandByPoint(ll)):(this.boundingBox.expandByPoint(sl.min),this.boundingBox.expandByPoint(sl.max))}}else this.boundingBox.makeEmpty();(isNaN(this.boundingBox.min.x)||isNaN(this.boundingBox.min.y)||isNaN(this.boundingBox.min.z))&&q(`BufferGeometry.computeBoundingBox(): Computed min/max have NaN values. The "position" attribute is likely to have NaN values.`,this)}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new nl);let e=this.attributes.position,t=this.morphAttributes.position;if(e&&e.isGLBufferAttribute){q(`BufferGeometry.computeBoundingSphere(): GLBufferAttribute requires a manual bounding sphere.`,this),this.boundingSphere.set(new X,1/0);return}if(e){let n=this.boundingSphere.center;if(sl.setFromBufferAttribute(e),t)for(let e=0,n=t.length;e<n;e++){let n=t[e];cl.setFromBufferAttribute(n),this.morphTargetsRelative?(ll.addVectors(sl.min,cl.min),sl.expandByPoint(ll),ll.addVectors(sl.max,cl.max),sl.expandByPoint(ll)):(sl.expandByPoint(cl.min),sl.expandByPoint(cl.max))}sl.getCenter(n);let r=0;for(let t=0,i=e.count;t<i;t++)ll.fromBufferAttribute(e,t),r=Math.max(r,n.distanceToSquared(ll));if(t)for(let i=0,a=t.length;i<a;i++){let a=t[i],o=this.morphTargetsRelative;for(let t=0,i=a.count;t<i;t++)ll.fromBufferAttribute(a,t),o&&(ol.fromBufferAttribute(e,t),ll.add(ol)),r=Math.max(r,n.distanceToSquared(ll))}this.boundingSphere.radius=Math.sqrt(r),isNaN(this.boundingSphere.radius)&&q(`BufferGeometry.computeBoundingSphere(): Computed radius is NaN. The "position" attribute is likely to have NaN values.`,this)}}computeTangents(){let e=this.index,t=this.attributes;if(e===null||t.position===void 0||t.normal===void 0||t.uv===void 0){q(`BufferGeometry: .computeTangents() failed. Missing required attributes (index, position, normal or uv)`);return}let n=t.position,r=t.normal,i=t.uv,a=this.getAttribute(`tangent`);(a===void 0||a.count!==n.count)&&(a=new Yc(new Float32Array(4*n.count),4),this.setAttribute(`tangent`,a));let o=[],s=[];for(let e=0;e<n.count;e++)o[e]=new X,s[e]=new X;let c=new X,l=new X,u=new X,d=new Y,f=new Y,p=new Y,m=new X,h=new X;function g(e,t,r){c.fromBufferAttribute(n,e),l.fromBufferAttribute(n,t),u.fromBufferAttribute(n,r),d.fromBufferAttribute(i,e),f.fromBufferAttribute(i,t),p.fromBufferAttribute(i,r),l.sub(c),u.sub(c),f.sub(d),p.sub(d);let a=1/(f.x*p.y-p.x*f.y);isFinite(a)&&(m.copy(l).multiplyScalar(p.y).addScaledVector(u,-f.y).multiplyScalar(a),h.copy(u).multiplyScalar(f.x).addScaledVector(l,-p.x).multiplyScalar(a),o[e].add(m),o[t].add(m),o[r].add(m),s[e].add(h),s[t].add(h),s[r].add(h))}let _=this.groups;_.length===0&&(_=[{start:0,count:e.count}]);for(let t=0,n=_.length;t<n;++t){let n=_[t],r=n.start,i=n.count;for(let t=r,n=r+i;t<n;t+=3)g(e.getX(t+0),e.getX(t+1),e.getX(t+2))}let v=new X,y=new X,b=new X,x=new X;function S(e){b.fromBufferAttribute(r,e),x.copy(b);let t=o[e];v.copy(t),v.sub(b.multiplyScalar(b.dot(t))).normalize(),y.crossVectors(x,t);let n=y.dot(s[e])<0?-1:1;a.setXYZW(e,v.x,v.y,v.z,n)}for(let t=0,n=_.length;t<n;++t){let n=_[t],r=n.start,i=n.count;for(let t=r,n=r+i;t<n;t+=3)S(e.getX(t+0)),S(e.getX(t+1)),S(e.getX(t+2))}this._transformed=!0}computeVertexNormals(){let e=this.index,t=this.getAttribute(`position`);if(t!==void 0){let n=this.getAttribute(`normal`);if(n===void 0||n.count!==t.count)n=new Yc(new Float32Array(t.count*3),3),this.setAttribute(`normal`,n);else for(let e=0,t=n.count;e<t;e++)n.setXYZ(e,0,0,0);let r=new X,i=new X,a=new X,o=new X,s=new X,c=new X,l=new X,u=new X;if(e)for(let d=0,f=e.count;d<f;d+=3){let f=e.getX(d+0),p=e.getX(d+1),m=e.getX(d+2);r.fromBufferAttribute(t,f),i.fromBufferAttribute(t,p),a.fromBufferAttribute(t,m),l.subVectors(a,i),u.subVectors(r,i),l.cross(u),o.fromBufferAttribute(n,f),s.fromBufferAttribute(n,p),c.fromBufferAttribute(n,m),o.add(l),s.add(l),c.add(l),n.setXYZ(f,o.x,o.y,o.z),n.setXYZ(p,s.x,s.y,s.z),n.setXYZ(m,c.x,c.y,c.z)}else for(let e=0,o=t.count;e<o;e+=3)r.fromBufferAttribute(t,e+0),i.fromBufferAttribute(t,e+1),a.fromBufferAttribute(t,e+2),l.subVectors(a,i),u.subVectors(r,i),l.cross(u),n.setXYZ(e+0,l.x,l.y,l.z),n.setXYZ(e+1,l.x,l.y,l.z),n.setXYZ(e+2,l.x,l.y,l.z);this.normalizeNormals(),n.needsUpdate=!0}}normalizeNormals(){let e=this.attributes.normal;for(let t=0,n=e.count;t<n;t++)ll.fromBufferAttribute(e,t),ll.normalize(),e.setXYZ(t,ll.x,ll.y,ll.z)}toNonIndexed(){function t(e,t){let n=e.array,r=e.itemSize,i=e.normalized,a=new n.constructor(t.length*r),o=0,s=0;for(let i=0,c=t.length;i<c;i++){o=e.isInterleavedBufferAttribute?t[i]*e.data.stride+e.offset:t[i]*r;for(let e=0;e<r;e++)a[s++]=n[o++]}return new Yc(a,r,i)}if(this.index===null)return K(`BufferGeometry.toNonIndexed(): BufferGeometry is already non-indexed.`),this;let n=new e,r=this.index.array,i=this.attributes;for(let e in i){let a=i[e],o=t(a,r);n.setAttribute(e,o)}let a=this.morphAttributes;for(let e in a){let i=[],o=a[e];for(let e=0,n=o.length;e<n;e++){let n=o[e],a=t(n,r);i.push(a)}n.morphAttributes[e]=i}n.morphTargetsRelative=this.morphTargetsRelative;let o=this.groups;for(let e=0,t=o.length;e<t;e++){let t=o[e];n.addGroup(t.start,t.count,t.materialIndex)}return n}toJSON(){let e={metadata:{version:4.7,type:`BufferGeometry`,generator:`BufferGeometry.toJSON`}};if(e.uuid=this.uuid,e.type=this.parameters!==void 0&&this._transformed===!0?`BufferGeometry`:this.type,e.name=this.name,Object.keys(this.userData).length>0&&(e.userData=this.userData),this.parameters!==void 0&&this._transformed!==!0){let t=this.parameters;for(let n in t)t[n]!==void 0&&(e[n]=t[n]);return e}e.data={attributes:{}};let t=this.index;t!==null&&(e.data.index={type:t.array.constructor.name,array:Array.prototype.slice.call(t.array)});let n=this.attributes;for(let t in n){let r=n[t];e.data.attributes[t]=r.toJSON(e.data)}let r={},i=!1;for(let t in this.morphAttributes){let n=this.morphAttributes[t],a=[];for(let t=0,r=n.length;t<r;t++){let r=n[t];a.push(r.toJSON(e.data))}a.length>0&&(r[t]=a,i=!0)}i&&(e.data.morphAttributes=r,e.data.morphTargetsRelative=this.morphTargetsRelative);let a=this.groups;a.length>0&&(e.data.groups=JSON.parse(JSON.stringify(a)));let o=this.boundingSphere;return o!==null&&(e.data.boundingSphere=o.toJSON()),e}clone(){return new this.constructor().copy(this)}copy(e){this.index=null,this.attributes={},this.morphAttributes={},this.groups=[],this.boundingBox=null,this.boundingSphere=null;let t={};this.name=e.name;let n=e.index;n!==null&&this.setIndex(n.clone());let r=e.attributes;for(let e in r){let n=r[e];this.setAttribute(e,n.clone(t))}let i=e.morphAttributes;for(let e in i){let n=[],r=i[e];for(let e=0,i=r.length;e<i;e++)n.push(r[e].clone(t));this.morphAttributes[e]=n}this.morphTargetsRelative=e.morphTargetsRelative;let a=e.groups;for(let e=0,t=a.length;e<t;e++){let t=a[e];this.addGroup(t.start,t.count,t.materialIndex)}let o=e.boundingBox;o!==null&&(this.boundingBox=o.clone());let s=e.boundingSphere;return s!==null&&(this.boundingSphere=s.clone()),this.drawRange.start=e.drawRange.start,this.drawRange.count=e.drawRange.count,this.userData=e.userData,this._transformed=e._transformed,this}dispose(){this.dispatchEvent({type:`dispose`})}},dl=class{constructor(e,t){this.isInterleavedBuffer=!0,this.array=e,this.stride=t,this.count=e===void 0?0:e.length/t,this.usage=Eo,this.updateRanges=[],this.version=0,this.uuid=Uo()}onUploadCallback(){}set needsUpdate(e){e===!0&&this.version++}setUsage(e){return this.usage=e,this}addUpdateRange(e,t){this.updateRanges.push({start:e,count:t})}clearUpdateRanges(){this.updateRanges.length=0}copy(e){return this.array=new e.array.constructor(e.array),this.count=e.count,this.stride=e.stride,this.usage=e.usage,this}copyAt(e,t,n){e*=this.stride,n*=t.stride;for(let r=0,i=this.stride;r<i;r++)this.array[e+r]=t.array[n+r];return this}set(e,t=0){return this.array.set(e,t),this}clone(e){e.arrayBuffers===void 0&&(e.arrayBuffers={}),this.array.buffer._uuid===void 0&&(this.array.buffer._uuid=Uo()),e.arrayBuffers[this.array.buffer._uuid]===void 0&&(e.arrayBuffers[this.array.buffer._uuid]=this.array.slice(0).buffer);let t=new this.array.constructor(e.arrayBuffers[this.array.buffer._uuid]),n=new this.constructor(t,this.stride);return n.setUsage(this.usage),n}onUpload(e){return this.onUploadCallback=e,this}toJSON(e){e.arrayBuffers===void 0&&(e.arrayBuffers={}),this.array.buffer._uuid===void 0&&(this.array.buffer._uuid=Uo()),e.arrayBuffers[this.array.buffer._uuid]===void 0&&(e.arrayBuffers[this.array.buffer._uuid]=Array.from(new Uint32Array(this.array.buffer)));let t={uuid:this.uuid,buffer:this.array.buffer._uuid,type:this.array.constructor.name,stride:this.stride};return t.usage=this.usage,t}},fl=new X,pl=class e{constructor(e,t,n,r=!1){this.isInterleavedBufferAttribute=!0,this.name=``,this.data=e,this.itemSize=t,this.offset=n,this.normalized=r}get count(){return this.data.count}get array(){return this.data.array}set needsUpdate(e){this.data.needsUpdate=e}applyMatrix4(e){for(let t=0,n=this.data.count;t<n;t++)fl.fromBufferAttribute(this,t),fl.applyMatrix4(e),this.setXYZ(t,fl.x,fl.y,fl.z);return this}applyNormalMatrix(e){for(let t=0,n=this.count;t<n;t++)fl.fromBufferAttribute(this,t),fl.applyNormalMatrix(e),this.setXYZ(t,fl.x,fl.y,fl.z);return this}transformDirection(e){for(let t=0,n=this.count;t<n;t++)fl.fromBufferAttribute(this,t),fl.transformDirection(e),this.setXYZ(t,fl.x,fl.y,fl.z);return this}getComponent(e,t){let n=this.array[e*this.data.stride+this.offset+t];return this.normalized&&(n=cs(n,this.array)),n}setComponent(e,t,n){return this.normalized&&(n=ls(n,this.array)),this.data.array[e*this.data.stride+this.offset+t]=n,this}setX(e,t){return this.normalized&&(t=ls(t,this.array)),this.data.array[e*this.data.stride+this.offset]=t,this}setY(e,t){return this.normalized&&(t=ls(t,this.array)),this.data.array[e*this.data.stride+this.offset+1]=t,this}setZ(e,t){return this.normalized&&(t=ls(t,this.array)),this.data.array[e*this.data.stride+this.offset+2]=t,this}setW(e,t){return this.normalized&&(t=ls(t,this.array)),this.data.array[e*this.data.stride+this.offset+3]=t,this}getX(e){let t=this.data.array[e*this.data.stride+this.offset];return this.normalized&&(t=cs(t,this.array)),t}getY(e){let t=this.data.array[e*this.data.stride+this.offset+1];return this.normalized&&(t=cs(t,this.array)),t}getZ(e){let t=this.data.array[e*this.data.stride+this.offset+2];return this.normalized&&(t=cs(t,this.array)),t}getW(e){let t=this.data.array[e*this.data.stride+this.offset+3];return this.normalized&&(t=cs(t,this.array)),t}setXY(e,t,n){return e=e*this.data.stride+this.offset,this.normalized&&(t=ls(t,this.array),n=ls(n,this.array)),this.data.array[e+0]=t,this.data.array[e+1]=n,this}setXYZ(e,t,n,r){return e=e*this.data.stride+this.offset,this.normalized&&(t=ls(t,this.array),n=ls(n,this.array),r=ls(r,this.array)),this.data.array[e+0]=t,this.data.array[e+1]=n,this.data.array[e+2]=r,this}setXYZW(e,t,n,r,i){return e=e*this.data.stride+this.offset,this.normalized&&(t=ls(t,this.array),n=ls(n,this.array),r=ls(r,this.array),i=ls(i,this.array)),this.data.array[e+0]=t,this.data.array[e+1]=n,this.data.array[e+2]=r,this.data.array[e+3]=i,this}clone(t){if(t===void 0){No(`InterleavedBufferAttribute.clone(): Cloning an interleaved buffer attribute will de-interleave buffer data.`);let e=[];for(let t=0;t<this.count;t++){let n=t*this.data.stride+this.offset;for(let t=0;t<this.itemSize;t++)e.push(this.data.array[n+t])}return new Yc(new this.array.constructor(e),this.itemSize,this.normalized)}return t.interleavedBuffers===void 0&&(t.interleavedBuffers={}),t.interleavedBuffers[this.data.uuid]===void 0&&(t.interleavedBuffers[this.data.uuid]=this.data.clone(t)),new e(t.interleavedBuffers[this.data.uuid],this.itemSize,this.offset,this.normalized)}toJSON(e){if(e===void 0){No(`InterleavedBufferAttribute.toJSON(): Serializing an interleaved buffer attribute will de-interleave buffer data.`);let e=[];for(let t=0;t<this.count;t++){let n=t*this.data.stride+this.offset;for(let t=0;t<this.itemSize;t++)e.push(this.data.array[n+t])}return{itemSize:this.itemSize,type:this.array.constructor.name,array:e,normalized:this.normalized}}return e.interleavedBuffers===void 0&&(e.interleavedBuffers={}),e.interleavedBuffers[this.data.uuid]===void 0&&(e.interleavedBuffers[this.data.uuid]=this.data.toJSON(e)),{isInterleavedBufferAttribute:!0,itemSize:this.itemSize,data:this.data.uuid,offset:this.offset,normalized:this.normalized}}},ml=new X,hl=new X,gl=new Z,_l=class{constructor(e=new X(1,0,0),t=0){this.isPlane=!0,this.normal=e,this.constant=t}set(e,t){return this.normal.copy(e),this.constant=t,this}setComponents(e,t,n,r){return this.normal.set(e,t,n),this.constant=r,this}setFromNormalAndCoplanarPoint(e,t){return this.normal.copy(e),this.constant=-t.dot(this.normal),this}setFromCoplanarPoints(e,t,n){let r=ml.subVectors(n,t).cross(hl.subVectors(e,t)).normalize();return this.setFromNormalAndCoplanarPoint(r,e),this}copy(e){return this.normal.copy(e.normal),this.constant=e.constant,this}normalize(){let e=1/this.normal.length();return this.normal.multiplyScalar(e),this.constant*=e,this}negate(){return this.constant*=-1,this.normal.negate(),this}distanceToPoint(e){return this.normal.dot(e)+this.constant}distanceToSphere(e){return this.distanceToPoint(e.center)-e.radius}projectPoint(e,t){return t.copy(e).addScaledVector(this.normal,-this.distanceToPoint(e))}intersectLine(e,t,n=!0){let r=e.delta(ml),i=this.normal.dot(r);if(i===0)return this.distanceToPoint(e.start)===0?t.copy(e.start):null;let a=-(e.start.dot(this.normal)+this.constant)/i;return n===!0&&(a<0||a>1)?null:t.copy(e.start).addScaledVector(r,a)}intersectsLine(e){let t=this.distanceToPoint(e.start),n=this.distanceToPoint(e.end);return t<0&&n>0||n<0&&t>0}intersectsBox(e){return e.intersectsPlane(this)}intersectsSphere(e){return e.intersectsPlane(this)}coplanarPoint(e){return e.copy(this.normal).multiplyScalar(-this.constant)}applyMatrix4(e,t){let n=t||gl.getNormalMatrix(e),r=this.coplanarPoint(ml).applyMatrix4(e),i=this.normal.applyMatrix3(n).normalize();return this.constant=-r.dot(i),this}translate(e){return this.constant-=e.dot(this.normal),this}equals(e){return e.normal.equals(this.normal)&&e.constant===this.constant}clone(){return new this.constructor().copy(this)}toJSON(){return{normal:this.normal.toArray(),constant:this.constant}}fromJSON(e){return this.normal.fromArray(e.normal),this.constant=e.constant,this}},vl=0,yl=class extends Ro{constructor(){super(),this.isMaterial=!0,Object.defineProperty(this,"id",{value:vl++}),this.uuid=Uo(),this.name=``,this.type=`Material`,this.blending=1,this.side=0,this.vertexColors=!1,this.opacity=1,this.transparent=!1,this.alphaHash=!1,this.blendSrc=204,this.blendDst=205,this.blendEquation=100,this.blendSrcAlpha=null,this.blendDstAlpha=null,this.blendEquationAlpha=null,this.blendColor=new mc(0,0,0),this.blendAlpha=0,this.depthFunc=3,this.depthTest=!0,this.depthWrite=!0,this.stencilWriteMask=255,this.stencilFunc=519,this.stencilRef=0,this.stencilFuncMask=255,this.stencilFail=To,this.stencilZFail=To,this.stencilZPass=To,this.stencilWrite=!1,this.clippingPlanes=null,this.clipIntersection=!1,this.clipShadows=!1,this.shadowSide=null,this.colorWrite=!0,this.precision=null,this.polygonOffset=!1,this.polygonOffsetFactor=0,this.polygonOffsetUnits=0,this.dithering=!1,this.alphaToCoverage=!1,this.premultipliedAlpha=!1,this.forceSinglePass=!1,this.allowOverride=!0,this.visible=!0,this.toneMapped=!0,this.userData={},this.version=0,this._alphaTest=0}get alphaTest(){return this._alphaTest}set alphaTest(e){this._alphaTest>0!=e>0&&this.version++,this._alphaTest=e}onBeforeRender(){}onBeforeCompile(){}customProgramCacheKey(){return this.onBeforeCompile.toString()}setValues(e){if(e!==void 0)for(let t in e){let n=e[t];if(n===void 0){K(`Material: parameter '${t}' has value of undefined.`);continue}let r=this[t];if(r===void 0){K(`Material: '${t}' is not a property of THREE.${this.type}.`);continue}r&&r.isColor?r.set(n):r&&r.isVector2&&n&&n.isVector2||r&&r.isEuler&&n&&n.isEuler||r&&r.isVector3&&n&&n.isVector3?r.copy(n):this[t]=n}}toJSON(e){let t=e===void 0||typeof e==`string`;t&&(e={textures:{},images:{}});let n={metadata:{version:4.7,type:`Material`,generator:`Material.toJSON`}};n.uuid=this.uuid,n.type=this.type,n.blending=this.blending,n.side=this.side,n.shadowSide=this.shadowSide,n.vertexColors=this.vertexColors,n.opacity=this.opacity,n.transparent=this.transparent,n.blendSrc=this.blendSrc,n.blendDst=this.blendDst,n.blendEquation=this.blendEquation,n.blendSrcAlpha=this.blendSrcAlpha,n.blendDstAlpha=this.blendDstAlpha,n.blendEquationAlpha=this.blendEquationAlpha,n.blendColor=this.blendColor.getHex(),n.blendAlpha=this.blendAlpha,n.depthFunc=this.depthFunc,n.depthTest=this.depthTest,n.depthWrite=this.depthWrite,n.colorWrite=this.colorWrite,n.clipIntersection=this.clipIntersection,n.clipShadows=this.clipShadows,n.stencilWriteMask=this.stencilWriteMask,n.stencilFunc=this.stencilFunc,n.stencilRef=this.stencilRef,n.stencilFuncMask=this.stencilFuncMask,n.stencilFail=this.stencilFail,n.stencilZFail=this.stencilZFail,n.stencilZPass=this.stencilZPass,n.stencilWrite=this.stencilWrite,n.polygonOffset=this.polygonOffset,n.polygonOffsetFactor=this.polygonOffsetFactor,n.polygonOffsetUnits=this.polygonOffsetUnits,n.dithering=this.dithering,n.alphaTest=this.alphaTest,n.alphaHash=this.alphaHash,n.alphaToCoverage=this.alphaToCoverage,n.premultipliedAlpha=this.premultipliedAlpha,n.forceSinglePass=this.forceSinglePass,n.allowOverride=this.allowOverride,n.visible=this.visible,n.toneMapped=this.toneMapped,n.name=this.name,this.color&&this.color.isColor&&(n.color=this.color.getHex()),this.roughness!==void 0&&(n.roughness=this.roughness),this.metalness!==void 0&&(n.metalness=this.metalness),this.sheen!==void 0&&(n.sheen=this.sheen),this.sheenColor&&this.sheenColor.isColor&&(n.sheenColor=this.sheenColor.getHex()),this.sheenRoughness!==void 0&&(n.sheenRoughness=this.sheenRoughness),this.emissive&&this.emissive.isColor&&(n.emissive=this.emissive.getHex()),this.emissiveIntensity!==void 0&&(n.emissiveIntensity=this.emissiveIntensity),this.specular&&this.specular.isColor&&(n.specular=this.specular.getHex()),this.specularIntensity!==void 0&&(n.specularIntensity=this.specularIntensity),this.specularColor&&this.specularColor.isColor&&(n.specularColor=this.specularColor.getHex()),this.shininess!==void 0&&(n.shininess=this.shininess),this.clearcoat!==void 0&&(n.clearcoat=this.clearcoat),this.clearcoatRoughness!==void 0&&(n.clearcoatRoughness=this.clearcoatRoughness),this.clearcoatMap&&this.clearcoatMap.isTexture&&(n.clearcoatMap=this.clearcoatMap.toJSON(e).uuid),this.clearcoatRoughnessMap&&this.clearcoatRoughnessMap.isTexture&&(n.clearcoatRoughnessMap=this.clearcoatRoughnessMap.toJSON(e).uuid),this.clearcoatNormalMap&&this.clearcoatNormalMap.isTexture&&(n.clearcoatNormalMap=this.clearcoatNormalMap.toJSON(e).uuid,n.clearcoatNormalScale=this.clearcoatNormalScale.toArray()),this.sheenColorMap&&this.sheenColorMap.isTexture&&(n.sheenColorMap=this.sheenColorMap.toJSON(e).uuid),this.sheenRoughnessMap&&this.sheenRoughnessMap.isTexture&&(n.sheenRoughnessMap=this.sheenRoughnessMap.toJSON(e).uuid),this.dispersion!==void 0&&(n.dispersion=this.dispersion),this.retroreflectivity!==void 0&&(n.retroreflectivity=this.retroreflectivity),this.iridescence!==void 0&&(n.iridescence=this.iridescence),this.iridescenceIOR!==void 0&&(n.iridescenceIOR=this.iridescenceIOR),this.iridescenceThicknessRange!==void 0&&(n.iridescenceThicknessRange=this.iridescenceThicknessRange),this.iridescenceMap&&this.iridescenceMap.isTexture&&(n.iridescenceMap=this.iridescenceMap.toJSON(e).uuid),this.iridescenceThicknessMap&&this.iridescenceThicknessMap.isTexture&&(n.iridescenceThicknessMap=this.iridescenceThicknessMap.toJSON(e).uuid),this.anisotropy!==void 0&&(n.anisotropy=this.anisotropy),this.anisotropyRotation!==void 0&&(n.anisotropyRotation=this.anisotropyRotation),this.anisotropyMap&&this.anisotropyMap.isTexture&&(n.anisotropyMap=this.anisotropyMap.toJSON(e).uuid),this.map&&this.map.isTexture&&(n.map=this.map.toJSON(e).uuid),this.matcap&&this.matcap.isTexture&&(n.matcap=this.matcap.toJSON(e).uuid),this.alphaMap&&this.alphaMap.isTexture&&(n.alphaMap=this.alphaMap.toJSON(e).uuid),this.lightMap&&this.lightMap.isTexture&&(n.lightMap=this.lightMap.toJSON(e).uuid,n.lightMapIntensity=this.lightMapIntensity),this.aoMap&&this.aoMap.isTexture&&(n.aoMap=this.aoMap.toJSON(e).uuid,n.aoMapIntensity=this.aoMapIntensity),this.bumpMap&&this.bumpMap.isTexture&&(n.bumpMap=this.bumpMap.toJSON(e).uuid,n.bumpScale=this.bumpScale),this.normalMap&&this.normalMap.isTexture&&(n.normalMap=this.normalMap.toJSON(e).uuid,n.normalMapType=this.normalMapType,n.normalScale=this.normalScale.toArray()),this.displacementMap&&this.displacementMap.isTexture&&(n.displacementMap=this.displacementMap.toJSON(e).uuid,n.displacementScale=this.displacementScale,n.displacementBias=this.displacementBias),this.roughnessMap&&this.roughnessMap.isTexture&&(n.roughnessMap=this.roughnessMap.toJSON(e).uuid),this.metalnessMap&&this.metalnessMap.isTexture&&(n.metalnessMap=this.metalnessMap.toJSON(e).uuid),this.emissiveMap&&this.emissiveMap.isTexture&&(n.emissiveMap=this.emissiveMap.toJSON(e).uuid),this.specularMap&&this.specularMap.isTexture&&(n.specularMap=this.specularMap.toJSON(e).uuid),this.specularIntensityMap&&this.specularIntensityMap.isTexture&&(n.specularIntensityMap=this.specularIntensityMap.toJSON(e).uuid),this.specularColorMap&&this.specularColorMap.isTexture&&(n.specularColorMap=this.specularColorMap.toJSON(e).uuid),this.envMap&&this.envMap.isTexture&&(n.envMap=this.envMap.toJSON(e).uuid,this.combine!==void 0&&(n.combine=this.combine)),this.envMapRotation!==void 0&&(n.envMapRotation=this.envMapRotation.toArray()),this.envMapIntensity!==void 0&&(n.envMapIntensity=this.envMapIntensity),this.reflectivity!==void 0&&(n.reflectivity=this.reflectivity),this.refractionRatio!==void 0&&(n.refractionRatio=this.refractionRatio),this.gradientMap&&this.gradientMap.isTexture&&(n.gradientMap=this.gradientMap.toJSON(e).uuid),this.transmission!==void 0&&(n.transmission=this.transmission),this.transmissionMap&&this.transmissionMap.isTexture&&(n.transmissionMap=this.transmissionMap.toJSON(e).uuid),this.thickness!==void 0&&(n.thickness=this.thickness),this.thicknessMap&&this.thicknessMap.isTexture&&(n.thicknessMap=this.thicknessMap.toJSON(e).uuid),this.attenuationDistance!==void 0&&(n.attenuationDistance=this.attenuationDistance),this.attenuationColor!==void 0&&(n.attenuationColor=this.attenuationColor.getHex()),this.size!==void 0&&(n.size=this.size),this.sizeAttenuation!==void 0&&(n.sizeAttenuation=this.sizeAttenuation),Array.isArray(this.clippingPlanes)&&this.clippingPlanes.length>0&&(n.clippingPlanes=this.clippingPlanes.map(e=>e.toJSON())),this.rotation!==void 0&&(n.rotation=this.rotation),this.depthPacking!==void 0&&(n.depthPacking=this.depthPacking),this.linewidth!==void 0&&(n.linewidth=this.linewidth),this.linecap!==void 0&&(n.linecap=this.linecap),this.linejoin!==void 0&&(n.linejoin=this.linejoin),this.dashSize!==void 0&&(n.dashSize=this.dashSize),this.gapSize!==void 0&&(n.gapSize=this.gapSize),this.scale!==void 0&&(n.scale=this.scale),this.wireframe!==void 0&&(n.wireframe=this.wireframe),this.wireframeLinewidth!==void 0&&(n.wireframeLinewidth=this.wireframeLinewidth),this.wireframeLinecap!==void 0&&(n.wireframeLinecap=this.wireframeLinecap),this.wireframeLinejoin!==void 0&&(n.wireframeLinejoin=this.wireframeLinejoin),this.flatShading!==void 0&&(n.flatShading=this.flatShading),this.fog!==void 0&&(n.fog=this.fog),Object.keys(this.userData).length>0&&(n.userData=this.userData);function r(e){let t=[];for(let n in e){let r=e[n];delete r.metadata,t.push(r)}return t}if(t){let t=r(e.textures),i=r(e.images);t.length>0&&(n.textures=t),i.length>0&&(n.images=i)}return n}fromJSON(e,t){if(e.uuid!==void 0&&(this.uuid=e.uuid),e.name!==void 0&&(this.name=e.name),e.color!==void 0&&this.color!==void 0&&this.color.setHex(e.color),e.roughness!==void 0&&(this.roughness=e.roughness),e.metalness!==void 0&&(this.metalness=e.metalness),e.sheen!==void 0&&(this.sheen=e.sheen),e.sheenColor!==void 0&&(this.sheenColor=new mc().setHex(e.sheenColor)),e.sheenRoughness!==void 0&&(this.sheenRoughness=e.sheenRoughness),e.emissive!==void 0&&this.emissive!==void 0&&this.emissive.setHex(e.emissive),e.specular!==void 0&&this.specular!==void 0&&this.specular.setHex(e.specular),e.specularIntensity!==void 0&&(this.specularIntensity=e.specularIntensity),e.specularColor!==void 0&&this.specularColor!==void 0&&this.specularColor.setHex(e.specularColor),e.shininess!==void 0&&(this.shininess=e.shininess),e.clearcoat!==void 0&&(this.clearcoat=e.clearcoat),e.clearcoatRoughness!==void 0&&(this.clearcoatRoughness=e.clearcoatRoughness),e.dispersion!==void 0&&(this.dispersion=e.dispersion),e.retroreflectivity!==void 0&&(this.retroreflectivity=e.retroreflectivity),e.iridescence!==void 0&&(this.iridescence=e.iridescence),e.iridescenceIOR!==void 0&&(this.iridescenceIOR=e.iridescenceIOR),e.iridescenceThicknessRange!==void 0&&(this.iridescenceThicknessRange=e.iridescenceThicknessRange),e.transmission!==void 0&&(this.transmission=e.transmission),e.thickness!==void 0&&(this.thickness=e.thickness),e.attenuationDistance!==void 0&&(this.attenuationDistance=e.attenuationDistance),e.attenuationColor!==void 0&&this.attenuationColor!==void 0&&this.attenuationColor.setHex(e.attenuationColor),e.anisotropy!==void 0&&(this.anisotropy=e.anisotropy),e.anisotropyRotation!==void 0&&(this.anisotropyRotation=e.anisotropyRotation),e.fog!==void 0&&(this.fog=e.fog),e.flatShading!==void 0&&(this.flatShading=e.flatShading),e.blending!==void 0&&(this.blending=e.blending),e.combine!==void 0&&(this.combine=e.combine),e.side!==void 0&&(this.side=e.side),e.shadowSide!==void 0&&(this.shadowSide=e.shadowSide),e.opacity!==void 0&&(this.opacity=e.opacity),e.transparent!==void 0&&(this.transparent=e.transparent),e.alphaTest!==void 0&&(this.alphaTest=e.alphaTest),e.alphaHash!==void 0&&(this.alphaHash=e.alphaHash),e.depthFunc!==void 0&&(this.depthFunc=e.depthFunc),e.depthTest!==void 0&&(this.depthTest=e.depthTest),e.depthWrite!==void 0&&(this.depthWrite=e.depthWrite),e.colorWrite!==void 0&&(this.colorWrite=e.colorWrite),e.clippingPlanes!==void 0&&(this.clippingPlanes=e.clippingPlanes.map(e=>new _l().fromJSON(e))),e.clipIntersection!==void 0&&(this.clipIntersection=e.clipIntersection),e.clipShadows!==void 0&&(this.clipShadows=e.clipShadows),e.depthPacking!==void 0&&(this.depthPacking=e.depthPacking),e.blendSrc!==void 0&&(this.blendSrc=e.blendSrc),e.blendDst!==void 0&&(this.blendDst=e.blendDst),e.blendEquation!==void 0&&(this.blendEquation=e.blendEquation),e.blendSrcAlpha!==void 0&&(this.blendSrcAlpha=e.blendSrcAlpha),e.blendDstAlpha!==void 0&&(this.blendDstAlpha=e.blendDstAlpha),e.blendEquationAlpha!==void 0&&(this.blendEquationAlpha=e.blendEquationAlpha),e.blendColor!==void 0&&this.blendColor!==void 0&&this.blendColor.setHex(e.blendColor),e.blendAlpha!==void 0&&(this.blendAlpha=e.blendAlpha),e.stencilWriteMask!==void 0&&(this.stencilWriteMask=e.stencilWriteMask),e.stencilFunc!==void 0&&(this.stencilFunc=e.stencilFunc),e.stencilRef!==void 0&&(this.stencilRef=e.stencilRef),e.stencilFuncMask!==void 0&&(this.stencilFuncMask=e.stencilFuncMask),e.stencilFail!==void 0&&(this.stencilFail=e.stencilFail),e.stencilZFail!==void 0&&(this.stencilZFail=e.stencilZFail),e.stencilZPass!==void 0&&(this.stencilZPass=e.stencilZPass),e.stencilWrite!==void 0&&(this.stencilWrite=e.stencilWrite),e.wireframe!==void 0&&(this.wireframe=e.wireframe),e.wireframeLinewidth!==void 0&&(this.wireframeLinewidth=e.wireframeLinewidth),e.wireframeLinecap!==void 0&&(this.wireframeLinecap=e.wireframeLinecap),e.wireframeLinejoin!==void 0&&(this.wireframeLinejoin=e.wireframeLinejoin),e.rotation!==void 0&&(this.rotation=e.rotation),e.linewidth!==void 0&&(this.linewidth=e.linewidth),e.linecap!==void 0&&(this.linecap=e.linecap),e.linejoin!==void 0&&(this.linejoin=e.linejoin),e.dashSize!==void 0&&(this.dashSize=e.dashSize),e.gapSize!==void 0&&(this.gapSize=e.gapSize),e.scale!==void 0&&(this.scale=e.scale),e.polygonOffset!==void 0&&(this.polygonOffset=e.polygonOffset),e.polygonOffsetFactor!==void 0&&(this.polygonOffsetFactor=e.polygonOffsetFactor),e.polygonOffsetUnits!==void 0&&(this.polygonOffsetUnits=e.polygonOffsetUnits),e.dithering!==void 0&&(this.dithering=e.dithering),e.alphaToCoverage!==void 0&&(this.alphaToCoverage=e.alphaToCoverage),e.premultipliedAlpha!==void 0&&(this.premultipliedAlpha=e.premultipliedAlpha),e.forceSinglePass!==void 0&&(this.forceSinglePass=e.forceSinglePass),e.allowOverride!==void 0&&(this.allowOverride=e.allowOverride),e.visible!==void 0&&(this.visible=e.visible),e.toneMapped!==void 0&&(this.toneMapped=e.toneMapped),e.userData!==void 0&&(this.userData=e.userData),e.vertexColors!==void 0&&(this.vertexColors=typeof e.vertexColors==`number`?e.vertexColors>0:e.vertexColors),e.size!==void 0&&(this.size=e.size),e.sizeAttenuation!==void 0&&(this.sizeAttenuation=e.sizeAttenuation),e.map!==void 0&&(this.map=t[e.map]||null),e.matcap!==void 0&&(this.matcap=t[e.matcap]||null),e.alphaMap!==void 0&&(this.alphaMap=t[e.alphaMap]||null),e.bumpMap!==void 0&&(this.bumpMap=t[e.bumpMap]||null),e.bumpScale!==void 0&&(this.bumpScale=e.bumpScale),e.normalMap!==void 0&&(this.normalMap=t[e.normalMap]||null),e.normalMapType!==void 0&&(this.normalMapType=e.normalMapType),e.normalScale!==void 0){let t=e.normalScale;Array.isArray(t)===!1&&(t=[t,t]),this.normalScale=new Y().fromArray(t)}return e.displacementMap!==void 0&&(this.displacementMap=t[e.displacementMap]||null),e.displacementScale!==void 0&&(this.displacementScale=e.displacementScale),e.displacementBias!==void 0&&(this.displacementBias=e.displacementBias),e.roughnessMap!==void 0&&(this.roughnessMap=t[e.roughnessMap]||null),e.metalnessMap!==void 0&&(this.metalnessMap=t[e.metalnessMap]||null),e.emissiveMap!==void 0&&(this.emissiveMap=t[e.emissiveMap]||null),e.emissiveIntensity!==void 0&&(this.emissiveIntensity=e.emissiveIntensity),e.specularMap!==void 0&&(this.specularMap=t[e.specularMap]||null),e.specularIntensityMap!==void 0&&(this.specularIntensityMap=t[e.specularIntensityMap]||null),e.specularColorMap!==void 0&&(this.specularColorMap=t[e.specularColorMap]||null),e.envMap!==void 0&&(this.envMap=t[e.envMap]||null),e.envMapRotation!==void 0&&this.envMapRotation.fromArray(e.envMapRotation),e.envMapIntensity!==void 0&&(this.envMapIntensity=e.envMapIntensity),e.reflectivity!==void 0&&(this.reflectivity=e.reflectivity),e.refractionRatio!==void 0&&(this.refractionRatio=e.refractionRatio),e.lightMap!==void 0&&(this.lightMap=t[e.lightMap]||null),e.lightMapIntensity!==void 0&&(this.lightMapIntensity=e.lightMapIntensity),e.aoMap!==void 0&&(this.aoMap=t[e.aoMap]||null),e.aoMapIntensity!==void 0&&(this.aoMapIntensity=e.aoMapIntensity),e.gradientMap!==void 0&&(this.gradientMap=t[e.gradientMap]||null),e.clearcoatMap!==void 0&&(this.clearcoatMap=t[e.clearcoatMap]||null),e.clearcoatRoughnessMap!==void 0&&(this.clearcoatRoughnessMap=t[e.clearcoatRoughnessMap]||null),e.clearcoatNormalMap!==void 0&&(this.clearcoatNormalMap=t[e.clearcoatNormalMap]||null),e.clearcoatNormalScale!==void 0&&(this.clearcoatNormalScale=new Y().fromArray(e.clearcoatNormalScale)),e.iridescenceMap!==void 0&&(this.iridescenceMap=t[e.iridescenceMap]||null),e.iridescenceThicknessMap!==void 0&&(this.iridescenceThicknessMap=t[e.iridescenceThicknessMap]||null),e.transmissionMap!==void 0&&(this.transmissionMap=t[e.transmissionMap]||null),e.thicknessMap!==void 0&&(this.thicknessMap=t[e.thicknessMap]||null),e.anisotropyMap!==void 0&&(this.anisotropyMap=t[e.anisotropyMap]||null),e.sheenColorMap!==void 0&&(this.sheenColorMap=t[e.sheenColorMap]||null),e.sheenRoughnessMap!==void 0&&(this.sheenRoughnessMap=t[e.sheenRoughnessMap]||null),this}clone(){return new this.constructor().copy(this)}copy(e){this.name=e.name,this.blending=e.blending,this.side=e.side,this.vertexColors=e.vertexColors,this.opacity=e.opacity,this.transparent=e.transparent,this.blendSrc=e.blendSrc,this.blendDst=e.blendDst,this.blendEquation=e.blendEquation,this.blendSrcAlpha=e.blendSrcAlpha,this.blendDstAlpha=e.blendDstAlpha,this.blendEquationAlpha=e.blendEquationAlpha,this.blendColor.copy(e.blendColor),this.blendAlpha=e.blendAlpha,this.depthFunc=e.depthFunc,this.depthTest=e.depthTest,this.depthWrite=e.depthWrite,this.stencilWriteMask=e.stencilWriteMask,this.stencilFunc=e.stencilFunc,this.stencilRef=e.stencilRef,this.stencilFuncMask=e.stencilFuncMask,this.stencilFail=e.stencilFail,this.stencilZFail=e.stencilZFail,this.stencilZPass=e.stencilZPass,this.stencilWrite=e.stencilWrite;let t=e.clippingPlanes,n=null;if(t!==null){let e=t.length;n=Array(e);for(let r=0;r!==e;++r)n[r]=t[r].clone()}return this.clippingPlanes=n,this.clipIntersection=e.clipIntersection,this.clipShadows=e.clipShadows,this.shadowSide=e.shadowSide,this.colorWrite=e.colorWrite,this.precision=e.precision,this.polygonOffset=e.polygonOffset,this.polygonOffsetFactor=e.polygonOffsetFactor,this.polygonOffsetUnits=e.polygonOffsetUnits,this.dithering=e.dithering,this.alphaTest=e.alphaTest,this.alphaHash=e.alphaHash,this.alphaToCoverage=e.alphaToCoverage,this.premultipliedAlpha=e.premultipliedAlpha,this.forceSinglePass=e.forceSinglePass,this.allowOverride=e.allowOverride,this.visible=e.visible,this.toneMapped=e.toneMapped,this.userData=JSON.parse(JSON.stringify(e.userData)),this}dispose(){this.dispatchEvent({type:`dispose`})}set needsUpdate(e){e===!0&&this.version++}},bl=new X,xl=new X,Sl=new X,Cl=new X,wl=class{constructor(e=new X,t=new X(0,0,-1)){this.origin=e,this.direction=t}set(e,t){return this.origin.copy(e),this.direction.copy(t),this}copy(e){return this.origin.copy(e.origin),this.direction.copy(e.direction),this}at(e,t){return t.copy(this.origin).addScaledVector(this.direction,e)}lookAt(e){return this.direction.copy(e).sub(this.origin).normalize(),this}recast(e){return this.origin.copy(this.at(e,bl)),this}closestPointToPoint(e,t){t.subVectors(e,this.origin);let n=t.dot(this.direction);return n<0?t.copy(this.origin):t.copy(this.origin).addScaledVector(this.direction,n)}distanceToPoint(e){return Math.sqrt(this.distanceSqToPoint(e))}distanceSqToPoint(e){let t=bl.subVectors(e,this.origin).dot(this.direction);return t<0?this.origin.distanceToSquared(e):(bl.copy(this.origin).addScaledVector(this.direction,t),bl.distanceToSquared(e))}distanceSqToSegment(e,t,n,r){xl.copy(e).add(t).multiplyScalar(.5),Sl.copy(t).sub(e).normalize(),Cl.copy(this.origin).sub(xl);let i=e.distanceTo(t)*.5,a=-this.direction.dot(Sl),o=Cl.dot(this.direction),s=-Cl.dot(Sl),c=Cl.lengthSq(),l=Math.abs(1-a*a),u,d,f,p;if(l>0){if(u=a*s-o,d=a*o-s,p=i*l,u>=0){if(d>=-p){if(d<=p){let e=1/l;u*=e,d*=e,f=u*(u+a*d+2*o)+d*(a*u+d+2*s)+c}else d=i,u=Math.max(0,-(a*d+o)),f=-u*u+d*(d+2*s)+c}else d=-i,u=Math.max(0,-(a*d+o)),f=-u*u+d*(d+2*s)+c}else d<=-p?(u=Math.max(0,-(-a*i+o)),d=u>0?-i:Math.min(Math.max(-i,-s),i),f=-u*u+d*(d+2*s)+c):d<=p?(u=0,d=Math.min(Math.max(-i,-s),i),f=d*(d+2*s)+c):(u=Math.max(0,-(a*i+o)),d=u>0?i:Math.min(Math.max(-i,-s),i),f=-u*u+d*(d+2*s)+c)}else d=a>0?-i:i,u=Math.max(0,-(a*d+o)),f=-u*u+d*(d+2*s)+c;return n&&n.copy(this.origin).addScaledVector(this.direction,u),r&&r.copy(xl).addScaledVector(Sl,d),f}intersectSphere(e,t){if(e.radius<0)return null;bl.subVectors(e.center,this.origin);let n=bl.dot(this.direction),r=bl.dot(bl)-n*n,i=e.radius*e.radius;if(r>i)return null;let a=Math.sqrt(i-r),o=n-a,s=n+a;return s<0?null:o<0?this.at(s,t):this.at(o,t)}intersectsSphere(e){return e.radius<0?!1:this.distanceSqToPoint(e.center)<=e.radius*e.radius}distanceToPlane(e){let t=e.normal.dot(this.direction);if(t===0)return e.distanceToPoint(this.origin)===0?0:null;let n=-(this.origin.dot(e.normal)+e.constant)/t;return n>=0?n:null}intersectPlane(e,t){let n=this.distanceToPlane(e);return n===null?null:this.at(n,t)}intersectsPlane(e){let t=e.distanceToPoint(this.origin);return t===0||e.normal.dot(this.direction)*t<0}intersectBox(e,t){let n,r,i,a,o,s,c=1/this.direction.x,l=1/this.direction.y,u=1/this.direction.z,d=this.origin;return c>=0?(n=(e.min.x-d.x)*c,r=(e.max.x-d.x)*c):(n=(e.max.x-d.x)*c,r=(e.min.x-d.x)*c),l>=0?(i=(e.min.y-d.y)*l,a=(e.max.y-d.y)*l):(i=(e.max.y-d.y)*l,a=(e.min.y-d.y)*l),n>a||i>r||((i>n||isNaN(n))&&(n=i),(a<r||isNaN(r))&&(r=a),u>=0?(o=(e.min.z-d.z)*u,s=(e.max.z-d.z)*u):(o=(e.max.z-d.z)*u,s=(e.min.z-d.z)*u),n>s||o>r)||((o>n||n!==n)&&(n=o),(s<r||r!==r)&&(r=s),r<0)?null:this.at(n>=0?n:r,t)}intersectsBox(e){return this.intersectBox(e,bl)!==null}intersectTriangle(e,t,n,r,i){let a=this.origin,o=this.direction,s=o.x,c=o.y,l=o.z,u=e.x-a.x,d=e.y-a.y,f=e.z-a.z,p=t.x-a.x,m=t.y-a.y,h=t.z-a.z,g=n.x-a.x,_=n.y-a.y,v=n.z-a.z,y=Math.abs(s),b=Math.abs(c),x=Math.abs(l),S,C,w,T,E,D,O,k,A,j,M,N;if(y>=b&&y>=x?(w=s,D=u,A=p,N=g,s>=0?(S=c,C=l,T=d,E=f,O=m,k=h,j=_,M=v):(S=l,C=c,T=f,E=d,O=h,k=m,j=v,M=_)):b>=x?(w=c,D=d,A=m,N=_,c>=0?(S=l,C=s,T=f,E=u,O=h,k=p,j=v,M=g):(S=s,C=l,T=u,E=f,O=p,k=h,j=g,M=v)):(w=l,D=f,A=h,N=v,l>=0?(S=s,C=c,T=u,E=d,O=p,k=m,j=g,M=_):(S=c,C=s,T=d,E=u,O=m,k=p,j=_,M=g)),w===0)return null;let P=S/w,F=C/w,ee=1/w,te=T-P*D,I=E-F*D,L=O-P*A,ne=k-F*A,re=j-P*N,ie=M-F*N,ae=re*ne-ie*L,oe=te*ie-I*re,se=L*I-ne*te;if(r){if(ae<0||oe<0||se<0)return null}else if((ae<0||oe<0||se<0)&&(ae>0||oe>0||se>0))return null;let ce=ae+oe+se;if(ce===0)return null;let le=ee*(ae*D+oe*A+se*N);return(ce>0?le<0:le>0)?null:this.at(le/ce,i)}applyMatrix4(e){return this.origin.applyMatrix4(e),this.direction.transformDirection(e),this}equals(e){return e.origin.equals(this.origin)&&e.direction.equals(this.direction)}clone(){return new this.constructor().copy(this)}},Tl=class extends yl{constructor(e){super(),this.isMeshBasicMaterial=!0,this.type=`MeshBasicMaterial`,this.color=new mc(16777215),this.map=null,this.lightMap=null,this.lightMapIntensity=1,this.aoMap=null,this.aoMapIntensity=1,this.specularMap=null,this.alphaMap=null,this.envMap=null,this.envMapRotation=new Ws,this.combine=0,this.reflectivity=1,this.refractionRatio=.98,this.wireframe=!1,this.wireframeLinewidth=1,this.wireframeLinecap=`round`,this.wireframeLinejoin=`round`,this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.lightMap=e.lightMap,this.lightMapIntensity=e.lightMapIntensity,this.aoMap=e.aoMap,this.aoMapIntensity=e.aoMapIntensity,this.specularMap=e.specularMap,this.alphaMap=e.alphaMap,this.envMap=e.envMap,this.envMapRotation.copy(e.envMapRotation),this.combine=e.combine,this.reflectivity=e.reflectivity,this.refractionRatio=e.refractionRatio,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.wireframeLinecap=e.wireframeLinecap,this.wireframeLinejoin=e.wireframeLinejoin,this.fog=e.fog,this}},El=new Ps,Dl=new wl,Ol=new nl,kl=new X,Al=new X,jl=new X,Ml=new X,Nl=new X,Pl=new X,Fl=new X,Il=new X,Ll=class extends sc{constructor(e=new ul,t=new Tl){super(),this.isMesh=!0,this.type=`Mesh`,this.geometry=e,this.material=t,this.morphTargetDictionary=void 0,this.morphTargetInfluences=void 0,this.count=1,this.updateMorphTargets()}copy(e,t){return super.copy(e,t),e.morphTargetInfluences!==void 0&&(this.morphTargetInfluences=e.morphTargetInfluences.slice()),e.morphTargetDictionary!==void 0&&(this.morphTargetDictionary=Object.assign({},e.morphTargetDictionary)),this.material=Array.isArray(e.material)?e.material.slice():e.material,this.geometry=e.geometry,this}updateMorphTargets(){let e=this.geometry.morphAttributes,t=Object.keys(e);if(t.length>0){let n=e[t[0]];if(n!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let e=0,t=n.length;e<t;e++){let t=n[e].name||String(e);this.morphTargetInfluences.push(0),this.morphTargetDictionary[t]=e}}}}getVertexPosition(e,t){let n=this.geometry,r=n.attributes.position,i=n.morphAttributes.position,a=n.morphTargetsRelative;t.fromBufferAttribute(r,e);let o=this.morphTargetInfluences;if(i&&o){Pl.set(0,0,0);for(let n=0,r=i.length;n<r;n++){let r=o[n],s=i[n];r!==0&&(Nl.fromBufferAttribute(s,e),a?Pl.addScaledVector(Nl,r):Pl.addScaledVector(Nl.sub(t),r))}t.add(Pl)}return t}intersectsFrustum(e){return e.intersectsObject(this)}raycast(e,t){let n=this.geometry,r=this.material,i=this.matrixWorld;r!==void 0&&(n.boundingSphere===null&&n.computeBoundingSphere(),Ol.copy(n.boundingSphere),Ol.applyMatrix4(i),Dl.copy(e.ray).recast(e.near),!(Ol.containsPoint(Dl.origin)===!1&&(Dl.intersectSphere(Ol,kl)===null||Dl.origin.distanceToSquared(kl)>(e.far-e.near)**2))&&(El.copy(i).invert(),Dl.copy(e.ray).applyMatrix4(El),(n.boundingBox===null||Dl.intersectsBox(n.boundingBox)!==!1)&&this._computeIntersections(e,t,Dl)))}_computeIntersections(e,t,n){let r,i=this.geometry,a=this.material,o=i.index,s=i.attributes.position,c=i.attributes.uv,l=i.attributes.uv1,u=i.attributes.normal,d=i.groups,f=i.drawRange;if(o!==null){if(Array.isArray(a))for(let i=0,s=d.length;i<s;i++){let s=d[i],p=a[s.materialIndex],m=Math.max(s.start,f.start),h=Math.min(o.count,Math.min(s.start+s.count,f.start+f.count));for(let i=m,a=h;i<a;i+=3){let a=o.getX(i),d=o.getX(i+1),f=o.getX(i+2);r=zl(this,p,e,n,c,l,u,a,d,f),r&&(r.faceIndex=Math.floor(i/3),r.face.materialIndex=s.materialIndex,t.push(r))}}else{let i=Math.max(0,f.start),s=Math.min(o.count,f.start+f.count);for(let d=i,f=s;d<f;d+=3){let i=o.getX(d),s=o.getX(d+1),f=o.getX(d+2);r=zl(this,a,e,n,c,l,u,i,s,f),r&&(r.faceIndex=Math.floor(d/3),t.push(r))}}}else if(s!==void 0){if(Array.isArray(a))for(let i=0,o=d.length;i<o;i++){let o=d[i],p=a[o.materialIndex],m=Math.max(o.start,f.start),h=Math.min(s.count,Math.min(o.start+o.count,f.start+f.count));for(let i=m,a=h;i<a;i+=3){let a=i,s=i+1,d=i+2;r=zl(this,p,e,n,c,l,u,a,s,d),r&&(r.faceIndex=Math.floor(i/3),r.face.materialIndex=o.materialIndex,t.push(r))}}else{let i=Math.max(0,f.start),o=Math.min(s.count,f.start+f.count);for(let s=i,d=o;s<d;s+=3){let i=s,o=s+1,d=s+2;r=zl(this,a,e,n,c,l,u,i,o,d),r&&(r.faceIndex=Math.floor(s/3),t.push(r))}}}}};function Rl(e,t,n,r,i,a,o,s){let c;if(c=t.side===1?r.intersectTriangle(o,a,i,!0,s):r.intersectTriangle(i,a,o,t.side===0,s),c===null)return null;Il.copy(s),Il.applyMatrix4(e.matrixWorld);let l=n.ray.origin.distanceTo(Il);return l<n.near||l>n.far?null:{distance:l,point:Il.clone(),object:e}}function zl(e,t,n,r,i,a,o,s,c,l){e.getVertexPosition(s,Al),e.getVertexPosition(c,jl),e.getVertexPosition(l,Ml);let u=Rl(e,t,n,r,Al,jl,Ml,Fl);if(u){let e=new X;Ac.getBarycoord(Fl,Al,jl,Ml,e),i&&(u.uv=Ac.getInterpolatedAttribute(i,s,c,l,e,new Y)),a&&(u.uv1=Ac.getInterpolatedAttribute(a,s,c,l,e,new Y)),o&&(u.normal=Ac.getInterpolatedAttribute(o,s,c,l,e,new X),u.normal.dot(r.direction)>0&&u.normal.multiplyScalar(-1));let t={a:s,b:c,c:l,normal:new X,materialIndex:0};Ac.getNormal(Al,jl,Ml,t.normal),u.face=t,u.barycoord=e}return u}var Bl=class extends Os{constructor(e=null,t=1,n=1,r,i,a,o,s,c=ta,l=ta,u,d){super(null,a,o,s,c,l,r,i,u,d),this.isDataTexture=!0,this.image={data:e,width:t,height:n},this.generateMipmaps=!1,this.flipY=!1,this.unpackAlignment=1}},Vl=new nl,Hl=new Y(.5,.5),Ul=new X,Wl=class{constructor(e=new _l,t=new _l,n=new _l,r=new _l,i=new _l,a=new _l){this.planes=[e,t,n,r,i,a]}set(e,t,n,r,i,a){let o=this.planes;return o[0].copy(e),o[1].copy(t),o[2].copy(n),o[3].copy(r),o[4].copy(i),o[5].copy(a),this}copy(e){let t=this.planes;for(let n=0;n<6;n++)t[n].copy(e.planes[n]);return this}setFromProjectionMatrix(e,t=Do,n=!1){let r=this.planes,i=e.elements,a=i[0],o=i[1],s=i[2],c=i[3],l=i[4],u=i[5],d=i[6],f=i[7],p=i[8],m=i[9],h=i[10],g=i[11],_=i[12],v=i[13],y=i[14],b=i[15];if(r[0].setComponents(c-a,f-l,g-p,b-_).normalize(),r[1].setComponents(c+a,f+l,g+p,b+_).normalize(),r[2].setComponents(c+o,f+u,g+m,b+v).normalize(),r[3].setComponents(c-o,f-u,g-m,b-v).normalize(),n)r[4].setComponents(s,d,h,y).normalize(),r[5].setComponents(c-s,f-d,g-h,b-y).normalize();else if(r[4].setComponents(c-s,f-d,g-h,b-y).normalize(),t===2e3)r[5].setComponents(c+s,f+d,g+h,b+y).normalize();else if(t===2001)r[5].setComponents(s,d,h,y).normalize();else throw Error(`THREE.Frustum.setFromProjectionMatrix(): Invalid coordinate system: `+t);return this}intersectsObject(e){if(e.boundingSphere!==void 0)e.boundingSphere===null&&e.computeBoundingSphere(),Vl.copy(e.boundingSphere).applyMatrix4(e.matrixWorld);else{let t=e.geometry;t.boundingSphere===null&&t.computeBoundingSphere(),Vl.copy(t.boundingSphere).applyMatrix4(e.matrixWorld)}return this.intersectsSphere(Vl)}intersectsSprite(e){return Vl.center.set(0,0,0),Vl.radius=.7071067811865476+Hl.distanceTo(e.center),Vl.applyMatrix4(e.matrixWorld),this.intersectsSphere(Vl)}intersectsSphere(e){let t=this.planes,n=e.center,r=-e.radius;for(let e=0;e<6;e++)if(t[e].distanceToPoint(n)<r)return!1;return!0}intersectsBox(e){let t=this.planes;for(let n=0;n<6;n++){let r=t[n];if(Ul.x=r.normal.x>0?e.max.x:e.min.x,Ul.y=r.normal.y>0?e.max.y:e.min.y,Ul.z=r.normal.z>0?e.max.z:e.min.z,r.distanceToPoint(Ul)<0)return!1}return!0}containsPoint(e){let t=this.planes;for(let n=0;n<6;n++)if(t[n].distanceToPoint(e)<0)return!1;return!0}clone(){return new this.constructor().copy(this)}},Gl=class extends yl{constructor(e){super(),this.isLineBasicMaterial=!0,this.type=`LineBasicMaterial`,this.color=new mc(16777215),this.map=null,this.linewidth=1,this.linecap=`round`,this.linejoin=`round`,this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.linewidth=e.linewidth,this.linecap=e.linecap,this.linejoin=e.linejoin,this.fog=e.fog,this}},Kl=new X,ql=new X,Jl=new Ps,Yl=new wl,Xl=new nl,Zl=new X,Ql=new X,$l=class extends sc{constructor(e=new ul,t=new Gl){super(),this.isLine=!0,this.type=`Line`,this.geometry=e,this.material=t,this.morphTargetDictionary=void 0,this.morphTargetInfluences=void 0,this.updateMorphTargets()}copy(e,t){return super.copy(e,t),this.material=Array.isArray(e.material)?e.material.slice():e.material,this.geometry=e.geometry,this}computeLineDistances(){let e=this.geometry;if(e.index===null){let t=e.attributes.position,n=[0];for(let e=1,r=t.count;e<r;e++)Kl.fromBufferAttribute(t,e-1),ql.fromBufferAttribute(t,e),n[e]=n[e-1],n[e]+=Kl.distanceTo(ql);e.setAttribute(`lineDistance`,new Qc(n,1))}else K(`Line.computeLineDistances(): Computation only possible with non-indexed BufferGeometry.`);return this}intersectsFrustum(e){return e.intersectsObject(this)}raycast(e,t){let n=this.geometry,r=this.matrixWorld,i=e.params.Line.threshold,a=n.drawRange;if(n.boundingSphere===null&&n.computeBoundingSphere(),Xl.copy(n.boundingSphere),Xl.applyMatrix4(r),Xl.radius+=i,e.ray.intersectsSphere(Xl)===!1)return;Jl.copy(r).invert(),Yl.copy(e.ray).applyMatrix4(Jl);let o=i/((this.scale.x+this.scale.y+this.scale.z)/3),s=o*o,c=this.isLineSegments?2:1,l=n.index,u=n.attributes.position;if(l!==null){let n=Math.max(0,a.start),r=Math.min(l.count,a.start+a.count);for(let i=n,a=r-1;i<a;i+=c){let n=l.getX(i),r=l.getX(i+1),a=eu(this,e,Yl,s,n,r,i);a&&t.push(a)}if(this.isLineLoop){let i=l.getX(r-1),a=l.getX(n),o=eu(this,e,Yl,s,i,a,r-1);o&&t.push(o)}}else{let n=Math.max(0,a.start),r=Math.min(u.count,a.start+a.count);for(let i=n,a=r-1;i<a;i+=c){let n=eu(this,e,Yl,s,i,i+1,i);n&&t.push(n)}if(this.isLineLoop){let i=eu(this,e,Yl,s,r-1,n,r-1);i&&t.push(i)}}}updateMorphTargets(){let e=this.geometry.morphAttributes,t=Object.keys(e);if(t.length>0){let n=e[t[0]];if(n!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let e=0,t=n.length;e<t;e++){let t=n[e].name||String(e);this.morphTargetInfluences.push(0),this.morphTargetDictionary[t]=e}}}}};function eu(e,t,n,r,i,a,o){let s=e.geometry.attributes.position;if(Kl.fromBufferAttribute(s,i),ql.fromBufferAttribute(s,a),n.distanceSqToSegment(Kl,ql,Zl,Ql)>r)return;Zl.applyMatrix4(e.matrixWorld);let c=t.ray.origin.distanceTo(Zl);if(!(c<t.near||c>t.far))return{distance:c,point:Ql.clone().applyMatrix4(e.matrixWorld),index:o,face:null,faceIndex:null,barycoord:null,object:e}}var tu=new X,nu=new X,ru=class extends $l{constructor(e,t){super(e,t),this.isLineSegments=!0,this.type=`LineSegments`}computeLineDistances(){let e=this.geometry;if(e.index===null){let t=e.attributes.position,n=[];for(let e=0,r=t.count;e<r;e+=2)tu.fromBufferAttribute(t,e),nu.fromBufferAttribute(t,e+1),n[e]=e===0?0:n[e-1],n[e+1]=n[e]+tu.distanceTo(nu);e.setAttribute(`lineDistance`,new Qc(n,1))}else K(`LineSegments.computeLineDistances(): Computation only possible with non-indexed BufferGeometry.`);return this}},iu=class extends yl{constructor(e){super(),this.isPointsMaterial=!0,this.type=`PointsMaterial`,this.color=new mc(16777215),this.map=null,this.alphaMap=null,this.size=1,this.sizeAttenuation=!0,this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.color.copy(e.color),this.map=e.map,this.alphaMap=e.alphaMap,this.size=e.size,this.sizeAttenuation=e.sizeAttenuation,this.fog=e.fog,this}},au=new Ps,ou=new wl,su=new nl,cu=new X,lu=class extends sc{constructor(e=new ul,t=new iu){super(),this.isPoints=!0,this.type=`Points`,this.geometry=e,this.material=t,this.morphTargetDictionary=void 0,this.morphTargetInfluences=void 0,this.updateMorphTargets()}copy(e,t){return super.copy(e,t),this.material=Array.isArray(e.material)?e.material.slice():e.material,this.geometry=e.geometry,this}intersectsFrustum(e){return e.intersectsObject(this)}raycast(e,t){let n=this.geometry,r=this.matrixWorld,i=e.params.Points.threshold,a=n.drawRange;if(n.boundingSphere===null&&n.computeBoundingSphere(),su.copy(n.boundingSphere),su.applyMatrix4(r),su.radius+=i,e.ray.intersectsSphere(su)===!1)return;au.copy(r).invert(),ou.copy(e.ray).applyMatrix4(au);let o=i/((this.scale.x+this.scale.y+this.scale.z)/3),s=o*o,c=n.index,l=n.attributes.position;if(c!==null){let n=Math.max(0,a.start),i=Math.min(c.count,a.start+a.count);for(let a=n,o=i;a<o;a++){let n=c.getX(a);cu.fromBufferAttribute(l,n),uu(cu,n,s,r,e,t,this)}}else{let n=Math.max(0,a.start),i=Math.min(l.count,a.start+a.count);for(let a=n,o=i;a<o;a++)cu.fromBufferAttribute(l,a),uu(cu,a,s,r,e,t,this)}}updateMorphTargets(){let e=this.geometry.morphAttributes,t=Object.keys(e);if(t.length>0){let n=e[t[0]];if(n!==void 0){this.morphTargetInfluences=[],this.morphTargetDictionary={};for(let e=0,t=n.length;e<t;e++){let t=n[e].name||String(e);this.morphTargetInfluences.push(0),this.morphTargetDictionary[t]=e}}}}};function uu(e,t,n,r,i,a,o){let s=ou.distanceSqToPoint(e);if(s<n){let n=new X;ou.closestPointToPoint(e,n),n.applyMatrix4(r);let c=i.ray.origin.distanceTo(n);if(c<i.near||c>i.far)return;a.push({distance:c,distanceToRay:Math.sqrt(s),point:n,index:t,face:null,faceIndex:null,barycoord:null,object:o})}}var du=class extends Os{constructor(e=[],t=301,n,r,i,a,o,s,c,l){super(e,t,n,r,i,a,o,s,c,l),this.isCubeTexture=!0,this.flipY=!1}get images(){return this.image}set images(e){this.image=e}},fu=class extends Os{constructor(e,t,n,r,i,a,o,s,c){super(e,t,n,r,i,a,o,s,c),this.isCanvasTexture=!0,this.needsUpdate=!0}},pu=class extends Os{constructor(e,t,n=fa,r,i,a,o=ta,s=ta,c,l=Ca,u=1){if(l!==1026&&l!==1027)throw Error(`THREE.DepthTexture: format must be either THREE.DepthFormat or THREE.DepthStencilFormat`);super({width:e,height:t,depth:u},r,i,a,o,s,l,n,c),this.isDepthTexture=!0,this.flipY=!1,this.generateMipmaps=!1,this.compareFunction=null}copy(e){return super.copy(e),this.source=new ws(Object.assign({},e.image)),this.compareFunction=e.compareFunction,this}toJSON(e){let t=super.toJSON(e);return t.compareFunction=this.compareFunction,t}},mu=class extends pu{constructor(e,t=fa,n=301,r,i,a=ta,o=ta,s,c=Ca){let l={width:e,height:e,depth:1},u=[l,l,l,l,l,l];super(e,e,t,n,r,i,a,o,s,c),this.image=u,this.isCubeDepthTexture=!0,this.isCubeTexture=!0}get images(){return this.image}set images(e){this.image=e}},hu=class extends Os{constructor(e=null){super(),this.sourceTexture=e,this.isExternalTexture=!0}copy(e){return super.copy(e),this.sourceTexture=e.sourceTexture,this}},gu=class e extends ul{constructor(e=1,t=1,n=1,r=1,i=1,a=1){super(),this.type=`BoxGeometry`,this.parameters={width:e,height:t,depth:n,widthSegments:r,heightSegments:i,depthSegments:a};let o=this;r=Math.floor(r),i=Math.floor(i),a=Math.floor(a);let s=[],c=[],l=[],u=[],d=0,f=0;p(`z`,`y`,`x`,-1,-1,n,t,e,a,i,0),p(`z`,`y`,`x`,1,-1,n,t,-e,a,i,1),p(`x`,`z`,`y`,1,1,e,n,t,r,a,2),p(`x`,`z`,`y`,1,-1,e,n,-t,r,a,3),p(`x`,`y`,`z`,1,-1,e,t,n,r,i,4),p(`x`,`y`,`z`,-1,-1,e,t,-n,r,i,5),this.setIndex(s),this.setAttribute(`position`,new Qc(c,3)),this.setAttribute(`normal`,new Qc(l,3)),this.setAttribute(`uv`,new Qc(u,2));function p(e,t,n,r,i,a,p,m,h,g,_){let v=a/h,y=p/g,b=a/2,x=p/2,S=m/2,C=h+1,w=g+1,T=0,E=0,D=new X;for(let a=0;a<w;a++){let o=a*y-x;for(let s=0;s<C;s++)D[e]=(s*v-b)*r,D[t]=o*i,D[n]=S,c.push(D.x,D.y,D.z),D[e]=0,D[t]=0,D[n]=m>0?1:-1,l.push(D.x,D.y,D.z),u.push(s/h),u.push(1-a/g),T+=1}for(let e=0;e<g;e++)for(let t=0;t<h;t++){let n=d+t+C*e,r=d+t+C*(e+1),i=d+(t+1)+C*(e+1),a=d+(t+1)+C*e;s.push(n,r,a),s.push(r,i,a),E+=6}o.addGroup(f,E,_),f+=E,d+=T}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(t){return new e(t.width,t.height,t.depth,t.widthSegments,t.heightSegments,t.depthSegments)}},_u=class{constructor(){this.type=`Curve`,this.arcLengthDivisions=200,this.needsUpdate=!1,this.cacheArcLengths=null}getPoint(){K(`Curve: .getPoint() not implemented.`)}getPointAt(e,t){let n=this.getUtoTmapping(e);return this.getPoint(n,t)}getPoints(e=5){let t=[];for(let n=0;n<=e;n++)t.push(this.getPoint(n/e));return t}getSpacedPoints(e=5){let t=[];for(let n=0;n<=e;n++)t.push(this.getPointAt(n/e));return t}getLength(){let e=this.getLengths();return e[e.length-1]}getLengths(e=this.arcLengthDivisions){if(this.cacheArcLengths&&this.cacheArcLengths.length===e+1&&!this.needsUpdate)return this.cacheArcLengths;this.needsUpdate=!1;let t=[],n,r=this.getPoint(0),i=0;t.push(0);for(let a=1;a<=e;a++)n=this.getPoint(a/e),i+=n.distanceTo(r),t.push(i),r=n;return this.cacheArcLengths=t,t}updateArcLengths(){this.needsUpdate=!0,this.getLengths()}getUtoTmapping(e,t=null){let n=this.getLengths(),r=0,i=n.length,a;a=t||e*n[i-1];let o=0,s=i-1,c;for(;o<=s;)if(r=Math.floor(o+(s-o)/2),c=n[r]-a,c<0)o=r+1;else if(c>0)s=r-1;else{s=r;break}if(r=s,n[r]===a)return r/(i-1);let l=n[r],u=n[r+1]-l,d=(a-l)/u;return(r+d)/(i-1)}getTangent(e,t){let n=1e-4,r=e-n,i=e+n;r<0&&(r=0),i>1&&(i=1);let a=this.getPoint(r),o=this.getPoint(i),s=t||(a.isVector2?new Y:new X);return s.copy(o).sub(a).normalize(),s}getTangentAt(e,t){let n=this.getUtoTmapping(e);return this.getTangent(n,t)}computeFrenetFrames(e,t=!1){let n=new X,r=[],i=[],a=[],o=new X,s=new Ps;for(let t=0;t<=e;t++){let n=t/e;r[t]=this.getTangentAt(n,new X)}i[0]=new X,a[0]=new X;let c=Number.MAX_VALUE,l=Math.abs(r[0].x),u=Math.abs(r[0].y),d=Math.abs(r[0].z);l<=c&&(c=l,n.set(1,0,0)),u<=c&&(c=u,n.set(0,1,0)),d<=c&&n.set(0,0,1),o.crossVectors(r[0],n).normalize(),i[0].crossVectors(r[0],o),a[0].crossVectors(r[0],i[0]);for(let t=1;t<=e;t++){if(i[t]=i[t-1].clone(),a[t]=a[t-1].clone(),o.crossVectors(r[t-1],r[t]),o.length()>2**-52){o.normalize();let e=Math.acos(J(r[t-1].dot(r[t]),-1,1));i[t].applyMatrix4(s.makeRotationAxis(o,e))}a[t].crossVectors(r[t],i[t])}if(t===!0){let t=Math.acos(J(i[0].dot(i[e]),-1,1));t/=e,r[0].dot(o.crossVectors(i[0],i[e]))>0&&(t=-t);for(let n=1;n<=e;n++)i[n].applyMatrix4(s.makeRotationAxis(r[n],t*n)),a[n].crossVectors(r[n],i[n])}return{tangents:r,normals:i,binormals:a}}clone(){return new this.constructor().copy(this)}copy(e){return this.arcLengthDivisions=e.arcLengthDivisions,this}toJSON(){let e={metadata:{version:4.7,type:`Curve`,generator:`Curve.toJSON`}};return e.arcLengthDivisions=this.arcLengthDivisions,e.type=this.type,e}fromJSON(e){return this.arcLengthDivisions=e.arcLengthDivisions,this}},vu=class extends _u{constructor(e=0,t=0,n=1,r=1,i=0,a=Math.PI*2,o=!1,s=0){super(),this.isEllipseCurve=!0,this.type=`EllipseCurve`,this.aX=e,this.aY=t,this.xRadius=n,this.yRadius=r,this.aStartAngle=i,this.aEndAngle=a,this.aClockwise=o,this.aRotation=s}getPoint(e,t=new Y){let n=t,r=Math.PI*2,i=this.aEndAngle-this.aStartAngle,a=Math.abs(i)<2**-52;for(;i<0;)i+=r;for(;i>r;)i-=r;i<2**-52&&(i=a?0:r),this.aClockwise===!0&&!a&&(i===r?i=-r:i-=r);let o=this.aStartAngle+e*i,s=this.aX+this.xRadius*Math.cos(o),c=this.aY+this.yRadius*Math.sin(o);if(this.aRotation!==0){let e=Math.cos(this.aRotation),t=Math.sin(this.aRotation),n=s-this.aX,r=c-this.aY;s=n*e-r*t+this.aX,c=n*t+r*e+this.aY}return n.set(s,c)}copy(e){return super.copy(e),this.aX=e.aX,this.aY=e.aY,this.xRadius=e.xRadius,this.yRadius=e.yRadius,this.aStartAngle=e.aStartAngle,this.aEndAngle=e.aEndAngle,this.aClockwise=e.aClockwise,this.aRotation=e.aRotation,this}toJSON(){let e=super.toJSON();return e.aX=this.aX,e.aY=this.aY,e.xRadius=this.xRadius,e.yRadius=this.yRadius,e.aStartAngle=this.aStartAngle,e.aEndAngle=this.aEndAngle,e.aClockwise=this.aClockwise,e.aRotation=this.aRotation,e}fromJSON(e){return super.fromJSON(e),this.aX=e.aX,this.aY=e.aY,this.xRadius=e.xRadius,this.yRadius=e.yRadius,this.aStartAngle=e.aStartAngle,this.aEndAngle=e.aEndAngle,this.aClockwise=e.aClockwise,this.aRotation=e.aRotation,this}},yu=class extends vu{constructor(e,t,n,r,i,a){super(e,t,n,n,r,i,a),this.isArcCurve=!0,this.type=`ArcCurve`}};function bu(){let e=0,t=0,n=0,r=0;function i(i,a,o,s){e=i,t=o,n=-3*i+3*a-2*o-s,r=2*i-2*a+o+s}return{initCatmullRom:function(e,t,n,r,a){i(t,n,a*(n-e),a*(r-t))},initNonuniformCatmullRom:function(e,t,n,r,a,o,s){let c=(t-e)/a-(n-e)/(a+o)+(n-t)/o,l=(n-t)/o-(r-t)/(o+s)+(r-n)/s;c*=o,l*=o,i(t,n,c,l)},calc:function(i){let a=i*i,o=a*i;return e+t*i+n*a+r*o}}}var xu=new X,Su=new X,Cu=new bu,wu=new bu,Tu=new bu,Eu=class extends _u{constructor(e=[],t=!1,n=`centripetal`,r=.5){super(),this.isCatmullRomCurve3=!0,this.type=`CatmullRomCurve3`,this.points=e,this.closed=t,this.curveType=n,this.tension=r}getPoint(e,t=new X){let n=t,r=this.points,i=r.length,a=(i-+!this.closed)*e,o=Math.floor(a),s=a-o;this.closed?o+=o>0?0:(Math.floor(Math.abs(o)/i)+1)*i:s===0&&o===i-1&&(o=i-2,s=1);let c,l;this.closed||o>0?c=r[(o-1)%i]:(Su.subVectors(r[0],r[1]).add(r[0]),c=Su);let u=r[o%i],d=r[(o+1)%i];if(this.closed||o+2<i?l=r[(o+2)%i]:(xu.subVectors(r[i-1],r[i-2]).add(r[i-1]),l=xu),this.curveType===`centripetal`||this.curveType===`chordal`){let e=this.curveType===`chordal`?.5:.25,t=c.distanceToSquared(u)**+e,n=u.distanceToSquared(d)**+e,r=d.distanceToSquared(l)**+e;n<1e-4&&(n=1),t<1e-4&&(t=n),r<1e-4&&(r=n),Cu.initNonuniformCatmullRom(c.x,u.x,d.x,l.x,t,n,r),wu.initNonuniformCatmullRom(c.y,u.y,d.y,l.y,t,n,r),Tu.initNonuniformCatmullRom(c.z,u.z,d.z,l.z,t,n,r)}else this.curveType===`catmullrom`&&(Cu.initCatmullRom(c.x,u.x,d.x,l.x,this.tension),wu.initCatmullRom(c.y,u.y,d.y,l.y,this.tension),Tu.initCatmullRom(c.z,u.z,d.z,l.z,this.tension));return n.set(Cu.calc(s),wu.calc(s),Tu.calc(s)),n}copy(e){super.copy(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){let n=e.points[t];this.points.push(n.clone())}return this.closed=e.closed,this.curveType=e.curveType,this.tension=e.tension,this}toJSON(){let e=super.toJSON();e.points=[];for(let t=0,n=this.points.length;t<n;t++){let n=this.points[t];e.points.push(n.toArray())}return e.closed=this.closed,e.curveType=this.curveType,e.tension=this.tension,e}fromJSON(e){super.fromJSON(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){let n=e.points[t];this.points.push(new X().fromArray(n))}return this.closed=e.closed,this.curveType=e.curveType,this.tension=e.tension,this}};function Du(e,t,n,r,i){let a=(r-t)*.5,o=(i-n)*.5,s=e*e,c=e*s;return(2*n-2*r+a+o)*c+(-3*n+3*r-2*a-o)*s+a*e+n}function Ou(e,t){let n=1-e;return n*n*t}function ku(e,t){return 2*(1-e)*e*t}function Au(e,t){return e*e*t}function ju(e,t,n,r){return Ou(e,t)+ku(e,n)+Au(e,r)}function Mu(e,t){let n=1-e;return n*n*n*t}function Nu(e,t){let n=1-e;return 3*n*n*e*t}function Pu(e,t){return 3*(1-e)*e*e*t}function Fu(e,t){return e*e*e*t}function Iu(e,t,n,r,i){return Mu(e,t)+Nu(e,n)+Pu(e,r)+Fu(e,i)}var Lu=class extends _u{constructor(e=new Y,t=new Y,n=new Y,r=new Y){super(),this.isCubicBezierCurve=!0,this.type=`CubicBezierCurve`,this.v0=e,this.v1=t,this.v2=n,this.v3=r}getPoint(e,t=new Y){let n=t,r=this.v0,i=this.v1,a=this.v2,o=this.v3;return n.set(Iu(e,r.x,i.x,a.x,o.x),Iu(e,r.y,i.y,a.y,o.y)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this.v3.copy(e.v3),this}toJSON(){let e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e.v3=this.v3.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this.v3.fromArray(e.v3),this}},Ru=class extends _u{constructor(e=new X,t=new X,n=new X,r=new X){super(),this.isCubicBezierCurve3=!0,this.type=`CubicBezierCurve3`,this.v0=e,this.v1=t,this.v2=n,this.v3=r}getPoint(e,t=new X){let n=t,r=this.v0,i=this.v1,a=this.v2,o=this.v3;return n.set(Iu(e,r.x,i.x,a.x,o.x),Iu(e,r.y,i.y,a.y,o.y),Iu(e,r.z,i.z,a.z,o.z)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this.v3.copy(e.v3),this}toJSON(){let e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e.v3=this.v3.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this.v3.fromArray(e.v3),this}},zu=class extends _u{constructor(e=new Y,t=new Y){super(),this.isLineCurve=!0,this.type=`LineCurve`,this.v1=e,this.v2=t}getPoint(e,t=new Y){let n=t;return e===1?n.copy(this.v2):(n.copy(this.v2).sub(this.v1),n.multiplyScalar(e).add(this.v1)),n}getPointAt(e,t){return this.getPoint(e,t)}getTangent(e,t=new Y){return t.subVectors(this.v2,this.v1).normalize()}getTangentAt(e,t){return this.getTangent(e,t)}copy(e){return super.copy(e),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){let e=super.toJSON();return e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}},Bu=class extends _u{constructor(e=new X,t=new X){super(),this.isLineCurve3=!0,this.type=`LineCurve3`,this.v1=e,this.v2=t}getPoint(e,t=new X){let n=t;return e===1?n.copy(this.v2):(n.copy(this.v2).sub(this.v1),n.multiplyScalar(e).add(this.v1)),n}getPointAt(e,t){return this.getPoint(e,t)}getTangent(e,t=new X){return t.subVectors(this.v2,this.v1).normalize()}getTangentAt(e,t){return this.getTangent(e,t)}copy(e){return super.copy(e),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){let e=super.toJSON();return e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}},Vu=class extends _u{constructor(e=new Y,t=new Y,n=new Y){super(),this.isQuadraticBezierCurve=!0,this.type=`QuadraticBezierCurve`,this.v0=e,this.v1=t,this.v2=n}getPoint(e,t=new Y){let n=t,r=this.v0,i=this.v1,a=this.v2;return n.set(ju(e,r.x,i.x,a.x),ju(e,r.y,i.y,a.y)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){let e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}},Hu=class extends _u{constructor(e=new X,t=new X,n=new X){super(),this.isQuadraticBezierCurve3=!0,this.type=`QuadraticBezierCurve3`,this.v0=e,this.v1=t,this.v2=n}getPoint(e,t=new X){let n=t,r=this.v0,i=this.v1,a=this.v2;return n.set(ju(e,r.x,i.x,a.x),ju(e,r.y,i.y,a.y),ju(e,r.z,i.z,a.z)),n}copy(e){return super.copy(e),this.v0.copy(e.v0),this.v1.copy(e.v1),this.v2.copy(e.v2),this}toJSON(){let e=super.toJSON();return e.v0=this.v0.toArray(),e.v1=this.v1.toArray(),e.v2=this.v2.toArray(),e}fromJSON(e){return super.fromJSON(e),this.v0.fromArray(e.v0),this.v1.fromArray(e.v1),this.v2.fromArray(e.v2),this}},Uu=Object.freeze({__proto__:null,ArcCurve:yu,CatmullRomCurve3:Eu,CubicBezierCurve:Lu,CubicBezierCurve3:Ru,EllipseCurve:vu,LineCurve:zu,LineCurve3:Bu,QuadraticBezierCurve:Vu,QuadraticBezierCurve3:Hu,SplineCurve:class extends _u{constructor(e=[]){super(),this.isSplineCurve=!0,this.type=`SplineCurve`,this.points=e}getPoint(e,t=new Y){let n=t,r=this.points,i=(r.length-1)*e,a=Math.floor(i),o=i-a,s=r[a===0?a:a-1],c=r[a],l=r[a>r.length-2?r.length-1:a+1],u=r[a>r.length-3?r.length-1:a+2];return n.set(Du(o,s.x,c.x,l.x,u.x),Du(o,s.y,c.y,l.y,u.y)),n}copy(e){super.copy(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){let n=e.points[t];this.points.push(n.clone())}return this}toJSON(){let e=super.toJSON();e.points=[];for(let t=0,n=this.points.length;t<n;t++){let n=this.points[t];e.points.push(n.toArray())}return e}fromJSON(e){super.fromJSON(e),this.points=[];for(let t=0,n=e.points.length;t<n;t++){let n=e.points[t];this.points.push(new Y().fromArray(n))}return this}}}),Wu=class e extends ul{constructor(e=1,t=1,n=1,r=1){super(),this.type=`PlaneGeometry`,this.parameters={width:e,height:t,widthSegments:n,heightSegments:r};let i=e/2,a=t/2,o=Math.floor(n),s=Math.floor(r),c=o+1,l=s+1,u=e/o,d=t/s,f=[],p=[],m=[],h=[];for(let e=0;e<l;e++){let t=e*d-a;for(let n=0;n<c;n++){let r=n*u-i;p.push(r,-t,0),m.push(0,0,1),h.push(n/o),h.push(1-e/s)}}for(let e=0;e<s;e++)for(let t=0;t<o;t++){let n=t+c*e,r=t+c*(e+1),i=t+1+c*(e+1),a=t+1+c*e;f.push(n,r,a),f.push(r,i,a)}this.setIndex(f),this.setAttribute(`position`,new Qc(p,3)),this.setAttribute(`normal`,new Qc(m,3)),this.setAttribute(`uv`,new Qc(h,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(t){return new e(t.width,t.height,t.widthSegments,t.heightSegments)}},Gu=class e extends ul{constructor(e=1,t=32,n=16,r=0,i=Math.PI*2,a=0,o=Math.PI){super(),this.type=`SphereGeometry`,this.parameters={radius:e,widthSegments:t,heightSegments:n,phiStart:r,phiLength:i,thetaStart:a,thetaLength:o},t=Math.max(3,Math.floor(t)),n=Math.max(2,Math.floor(n));let s=Math.min(a+o,Math.PI),c=0,l=[],u=new X,d=new X,f=[],p=[],m=[],h=[];for(let f=0;f<=n;f++){let g=[],_=f/n,v=a+_*o,y=e*Math.cos(v),b=Math.sqrt(e*e-y*y),x=0;f===0&&a===0?x=.5/t:f===n&&s===Math.PI&&(x=-.5/t);for(let e=0;e<=t;e++){let n=e/t,a=r+n*i;u.x=-b*Math.cos(a),u.y=y,u.z=b*Math.sin(a),p.push(u.x,u.y,u.z),d.copy(u).normalize(),m.push(d.x,d.y,d.z),h.push(n+x,1-_),g.push(c++)}l.push(g)}for(let e=0;e<n;e++)for(let r=0;r<t;r++){let t=l[e][r+1],i=l[e][r],o=l[e+1][r],c=l[e+1][r+1];(e!==0||a>0)&&f.push(t,i,c),(e!==n-1||s<Math.PI)&&f.push(i,o,c)}this.setIndex(f),this.setAttribute(`position`,new Qc(p,3)),this.setAttribute(`normal`,new Qc(m,3)),this.setAttribute(`uv`,new Qc(h,2))}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}static fromJSON(t){return new e(t.radius,t.widthSegments,t.heightSegments,t.phiStart,t.phiLength,t.thetaStart,t.thetaLength)}},Ku=class e extends ul{constructor(e=new Hu(new X(-1,-1,0),new X(-1,1,0),new X(1,1,0)),t=64,n=1,r=8,i=!1){super(),this.type=`TubeGeometry`,this.parameters={path:e,tubularSegments:t,radius:n,radialSegments:r,closed:i};let a=e.computeFrenetFrames(t,i);this.tangents=a.tangents,this.normals=a.normals,this.binormals=a.binormals;let o=new X,s=new X,c=new Y,l=new X,u=[],d=[],f=[],p=[];m(),this.setIndex(p),this.setAttribute(`position`,new Qc(u,3)),this.setAttribute(`normal`,new Qc(d,3)),this.setAttribute(`uv`,new Qc(f,2));function m(){for(let e=0;e<t;e++)h(e);h(i===!1?t:0),_(),g()}function h(i){l=e.getPointAt(i/t,l);let c=a.normals[i],f=a.binormals[i];for(let e=0;e<=r;e++){let t=e/r*Math.PI*2,i=Math.sin(t),a=-Math.cos(t);s.x=a*c.x+i*f.x,s.y=a*c.y+i*f.y,s.z=a*c.z+i*f.z,s.normalize(),d.push(s.x,s.y,s.z),o.x=l.x+n*s.x,o.y=l.y+n*s.y,o.z=l.z+n*s.z,u.push(o.x,o.y,o.z)}}function g(){for(let e=1;e<=t;e++)for(let t=1;t<=r;t++){let n=(r+1)*(e-1)+(t-1),i=(r+1)*e+(t-1),a=(r+1)*e+t,o=(r+1)*(e-1)+t;p.push(n,i,o),p.push(i,a,o)}}function _(){for(let e=0;e<=t;e++)for(let n=0;n<=r;n++)c.x=e/t,c.y=n/r,f.push(c.x,c.y)}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}toJSON(){let e=super.toJSON();return e.path=this.parameters.path.toJSON(),e}static fromJSON(t){return new e(new Uu[t.path.type]().fromJSON(t.path),t.tubularSegments,t.radius,t.radialSegments,t.closed)}},qu=class extends ul{constructor(e=null){if(super(),this.type=`WireframeGeometry`,this.parameters={geometry:e},e!==null){let t=[],n=new Set,r=new X,i=new X;if(e.index!==null){let a=e.attributes.position,o=e.index,s=e.groups;s.length===0&&(s=[{start:0,count:o.count,materialIndex:0}]);for(let e=0,c=s.length;e<c;++e){let c=s[e],l=c.start,u=c.count;for(let e=l,s=l+u;e<s;e+=3)for(let s=0;s<3;s++){let c=o.getX(e+s),l=o.getX(e+(s+1)%3);r.fromBufferAttribute(a,c),i.fromBufferAttribute(a,l),Ju(r,i,n)===!0&&(t.push(r.x,r.y,r.z),t.push(i.x,i.y,i.z))}}}else{let a=e.attributes.position;for(let e=0,o=a.count/3;e<o;e++)for(let o=0;o<3;o++){let s=3*e+o,c=3*e+(o+1)%3;r.fromBufferAttribute(a,s),i.fromBufferAttribute(a,c),Ju(r,i,n)===!0&&(t.push(r.x,r.y,r.z),t.push(i.x,i.y,i.z))}}this.setAttribute(`position`,new Qc(t,3))}}copy(e){return super.copy(e),this.parameters=Object.assign({},e.parameters),this}};function Ju(e,t,n){let r=`${e.x},${e.y},${e.z}-${t.x},${t.y},${t.z}`,i=`${t.x},${t.y},${t.z}-${e.x},${e.y},${e.z}`;return n.has(r)===!0||n.has(i)===!0?!1:(n.add(r),n.add(i),!0)}function Yu(e){let t={};for(let n in e){t[n]={};for(let r in e[n]){let i=e[n][r];if(Zu(i))i.isRenderTargetTexture?(K(`UniformsUtils: Textures of render targets cannot be cloned via cloneUniforms() or mergeUniforms().`),t[n][r]=null):t[n][r]=i.clone();else if(Array.isArray(i)){if(Zu(i[0])){let e=[];for(let t=0,n=i.length;t<n;t++)e[t]=i[t].clone();t[n][r]=e}else t[n][r]=i.slice()}else t[n][r]=i}}return t}function Xu(e){let t={};for(let n=0;n<e.length;n++){let r=Yu(e[n]);for(let e in r)t[e]=r[e]}return t}function Zu(e){return e&&(e.isColor||e.isMatrix3||e.isMatrix4||e.isVector2||e.isVector3||e.isVector4||e.isTexture||e.isQuaternion)}function Qu(e){let t=[];for(let n=0;n<e.length;n++)t.push(e[n].clone());return t}function $u(e){let t=e.getRenderTarget();return t===null?e.outputColorSpace:t.isXRRenderTarget===!0?t.texture.colorSpace:vs.workingColorSpace}var ed={clone:Yu,merge:Xu},td=`void main() {
	gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
}`,nd=`void main() {
	gl_FragColor = vec4( 1.0, 0.0, 0.0, 1.0 );
}`,rd=class extends yl{constructor(e){super(),this.isShaderMaterial=!0,this.type=`ShaderMaterial`,this.defines={},this.uniforms={},this.uniformsGroups=[],this.vertexShader=td,this.fragmentShader=nd,this.linewidth=1,this.wireframe=!1,this.wireframeLinewidth=1,this.fog=!1,this.lights=!1,this.clipping=!1,this.forceSinglePass=!0,this.extensions={clipCullDistance:!1,multiDraw:!1},this.defaultAttributeValues={color:[1,1,1],uv:[0,0],uv1:[0,0]},this.index0AttributeName=void 0,this.uniformsNeedUpdate=!1,this.glslVersion=null,e!==void 0&&this.setValues(e)}copy(e){return super.copy(e),this.fragmentShader=e.fragmentShader,this.vertexShader=e.vertexShader,this.uniforms=Yu(e.uniforms),this.uniformsGroups=Qu(e.uniformsGroups),this.defines=Object.assign({},e.defines),this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.fog=e.fog,this.lights=e.lights,this.clipping=e.clipping,this.extensions=Object.assign({},e.extensions),this.glslVersion=e.glslVersion,this.defaultAttributeValues=Object.assign({},e.defaultAttributeValues),this.index0AttributeName=e.index0AttributeName,this.uniformsNeedUpdate=e.uniformsNeedUpdate,this}toJSON(e){let t=super.toJSON(e);t.glslVersion=this.glslVersion,t.uniforms={};for(let n in this.uniforms){let r=this.uniforms[n].value;r&&r.isTexture?t.uniforms[n]={type:`t`,value:r.toJSON(e).uuid}:r&&r.isColor?t.uniforms[n]={type:`c`,value:r.getHex()}:r&&r.isVector2?t.uniforms[n]={type:`v2`,value:r.toArray()}:r&&r.isVector3?t.uniforms[n]={type:`v3`,value:r.toArray()}:r&&r.isVector4?t.uniforms[n]={type:`v4`,value:r.toArray()}:r&&r.isMatrix3?t.uniforms[n]={type:`m3`,value:r.toArray()}:r&&r.isMatrix4?t.uniforms[n]={type:`m4`,value:r.toArray()}:t.uniforms[n]={value:r}}Object.keys(this.defines).length>0&&(t.defines=this.defines),t.vertexShader=this.vertexShader,t.fragmentShader=this.fragmentShader,t.lights=this.lights,t.clipping=this.clipping;let n={};for(let e in this.extensions)this.extensions[e]===!0&&(n[e]=!0);return Object.keys(n).length>0&&(t.extensions=n),t}fromJSON(e,t){if(super.fromJSON(e,t),e.uniforms!==void 0)for(let n in e.uniforms){let r=e.uniforms[n];switch(this.uniforms[n]={},r.type){case`t`:this.uniforms[n].value=t[r.value]||null;break;case`c`:this.uniforms[n].value=new mc().setHex(r.value);break;case`v2`:this.uniforms[n].value=new Y().fromArray(r.value);break;case`v3`:this.uniforms[n].value=new X().fromArray(r.value);break;case`v4`:this.uniforms[n].value=new ks().fromArray(r.value);break;case`m3`:this.uniforms[n].value=new Z().fromArray(r.value);break;case`m4`:this.uniforms[n].value=new Ps().fromArray(r.value);break;default:this.uniforms[n].value=r.value}}if(e.defines!==void 0&&(this.defines=e.defines),e.vertexShader!==void 0&&(this.vertexShader=e.vertexShader),e.fragmentShader!==void 0&&(this.fragmentShader=e.fragmentShader),e.glslVersion!==void 0&&(this.glslVersion=e.glslVersion),e.extensions!==void 0)for(let t in e.extensions)this.extensions[t]=e.extensions[t];return e.lights!==void 0&&(this.lights=e.lights),e.clipping!==void 0&&(this.clipping=e.clipping),this}},id=class extends rd{constructor(e){super(e),this.isRawShaderMaterial=!0,this.type=`RawShaderMaterial`}},ad=class extends yl{constructor(e){super(),this.isMeshStandardMaterial=!0,this.type=`MeshStandardMaterial`,this.defines={STANDARD:``},this.color=new mc(16777215),this.roughness=1,this.metalness=0,this.map=null,this.lightMap=null,this.lightMapIntensity=1,this.aoMap=null,this.aoMapIntensity=1,this.emissive=new mc(0),this.emissiveIntensity=1,this.emissiveMap=null,this.bumpMap=null,this.bumpScale=1,this.normalMap=null,this.normalMapType=0,this.normalScale=new Y(1,1),this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.roughnessMap=null,this.metalnessMap=null,this.alphaMap=null,this.envMap=null,this.envMapRotation=new Ws,this.envMapIntensity=1,this.wireframe=!1,this.wireframeLinewidth=1,this.wireframeLinecap=`round`,this.wireframeLinejoin=`round`,this.flatShading=!1,this.fog=!0,this.setValues(e)}copy(e){return super.copy(e),this.defines={STANDARD:``},this.color.copy(e.color),this.roughness=e.roughness,this.metalness=e.metalness,this.map=e.map,this.lightMap=e.lightMap,this.lightMapIntensity=e.lightMapIntensity,this.aoMap=e.aoMap,this.aoMapIntensity=e.aoMapIntensity,this.emissive.copy(e.emissive),this.emissiveMap=e.emissiveMap,this.emissiveIntensity=e.emissiveIntensity,this.bumpMap=e.bumpMap,this.bumpScale=e.bumpScale,this.normalMap=e.normalMap,this.normalMapType=e.normalMapType,this.normalScale.copy(e.normalScale),this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this.roughnessMap=e.roughnessMap,this.metalnessMap=e.metalnessMap,this.alphaMap=e.alphaMap,this.envMap=e.envMap,this.envMapRotation.copy(e.envMapRotation),this.envMapIntensity=e.envMapIntensity,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this.wireframeLinecap=e.wireframeLinecap,this.wireframeLinejoin=e.wireframeLinejoin,this.flatShading=e.flatShading,this.fog=e.fog,this}},od=class extends yl{constructor(e){super(),this.isMeshDepthMaterial=!0,this.type=`MeshDepthMaterial`,this.depthPacking=bo,this.map=null,this.alphaMap=null,this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.wireframe=!1,this.wireframeLinewidth=1,this.setValues(e)}copy(e){return super.copy(e),this.depthPacking=e.depthPacking,this.map=e.map,this.alphaMap=e.alphaMap,this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this.wireframe=e.wireframe,this.wireframeLinewidth=e.wireframeLinewidth,this}},sd=class extends yl{constructor(e){super(),this.isMeshDistanceMaterial=!0,this.type=`MeshDistanceMaterial`,this.map=null,this.alphaMap=null,this.displacementMap=null,this.displacementScale=1,this.displacementBias=0,this.setValues(e)}copy(e){return super.copy(e),this.map=e.map,this.alphaMap=e.alphaMap,this.displacementMap=e.displacementMap,this.displacementScale=e.displacementScale,this.displacementBias=e.displacementBias,this}};function cd(e,t){return!e||e.constructor===t?e:typeof t.BYTES_PER_ELEMENT==`number`?new t(e):Array.prototype.slice.call(e)}function ld(e){return e!==void 0&&e.inTangents!==void 0&&e.outTangents!==void 0}var ud=class{constructor(e,t,n,r){this.parameterPositions=e,this._cachedIndex=0,this.resultBuffer=r===void 0?new t.constructor(n):r,this.sampleValues=t,this.valueSize=n,this.settings=null,this.DefaultSettings_={}}evaluate(e){let t=this.parameterPositions,n=this._cachedIndex,r=t[n],i=t[n-1];validate_interval:{seek:{let a;linear_scan:{forward_scan:if(!(e<r)){for(let a=n+2;;){if(r===void 0){if(e<i)break forward_scan;return n=t.length,this._cachedIndex=n,this.copySampleValue_(n-1)}if(n===a)break;if(i=r,r=t[++n],e<r)break seek}a=t.length;break linear_scan}if(!(e>=i)){let o=t[1];e<o&&(n=2,i=o);for(let a=n-2;;){if(i===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(n===a)break;if(r=i,i=t[--n-1],e>=i)break seek}a=n,n=0;break linear_scan}break validate_interval}for(;n<a;){let r=n+a>>>1;e<t[r]?a=r:n=r+1}if(r=t[n],i=t[n-1],i===void 0)return this._cachedIndex=0,this.copySampleValue_(0);if(r===void 0)return n=t.length,this._cachedIndex=n,this.copySampleValue_(n-1)}this._cachedIndex=n,this.intervalChanged_(n,i,r)}return this.interpolate_(n,i,e,r)}getSettings_(){return this.settings||this.DefaultSettings_}copySampleValue_(e){let t=this.resultBuffer,n=this.sampleValues,r=this.valueSize,i=e*r;for(let e=0;e!==r;++e)t[e]=n[i+e];return t}interpolate_(){throw Error(`THREE.Interpolant: Call to abstract method.`)}intervalChanged_(){}},dd=class extends ud{constructor(e,t,n,r){super(e,t,n,r),this._weightPrev=-0,this._offsetPrev=-0,this._weightNext=-0,this._offsetNext=-0,this.DefaultSettings_={endingStart:_o,endingEnd:_o}}intervalChanged_(e,t,n){let r=this.parameterPositions,i=e-2,a=e+1,o=r[i],s=r[a];if(o===void 0)switch(this.getSettings_().endingStart){case vo:i=e,o=2*t-n;break;case yo:i=r.length-2,o=t+r[i]-r[i+1];break;default:i=e,o=n}if(s===void 0)switch(this.getSettings_().endingEnd){case vo:a=e,s=2*n-t;break;case yo:a=1,s=n+r[1]-r[0];break;default:a=e-1,s=t}let c=(n-t)*.5,l=this.valueSize;this._weightPrev=c/(t-o),this._weightNext=c/(s-n),this._offsetPrev=i*l,this._offsetNext=a*l}interpolate_(e,t,n,r){let i=this.resultBuffer,a=this.sampleValues,o=this.valueSize,s=e*o,c=s-o,l=this._offsetPrev,u=this._offsetNext,d=this._weightPrev,f=this._weightNext,p=(n-t)/(r-t),m=p*p,h=m*p,g=-d*h+2*d*m-d*p,_=(1+d)*h+(-1.5-2*d)*m+(-.5+d)*p+1,v=(-1-f)*h+(1.5+f)*m+.5*p,y=f*h-f*m;for(let e=0;e!==o;++e)i[e]=g*a[l+e]+_*a[c+e]+v*a[s+e]+y*a[u+e];return i}},fd=class extends ud{constructor(e,t,n,r){super(e,t,n,r)}interpolate_(e,t,n,r){let i=this.resultBuffer,a=this.sampleValues,o=this.valueSize,s=e*o,c=s-o,l=(n-t)/(r-t),u=1-l;for(let e=0;e!==o;++e)i[e]=a[c+e]*u+a[s+e]*l;return i}},pd=class extends ud{constructor(e,t,n,r){super(e,t,n,r)}interpolate_(e){return this.copySampleValue_(e-1)}},md=class extends ud{interpolate_(e,t,n,r){let i=this.resultBuffer,a=this.sampleValues,o=this.valueSize,s=e*o,c=s-o,l=this.inTangents,u=this.outTangents;if(!l||!u){let e=(n-t)/(r-t),l=1-e;for(let t=0;t!==o;++t)i[t]=a[c+t]*l+a[s+t]*e;return i}let d=o*2,f=e-1;for(let p=0;p!==o;++p){let o=a[c+p],m=a[s+p],h=f*d+p*2,g=u[h],_=u[h+1],v=e*d+p*2,y=l[v],b=l[v+1],x=_d(n,t,g,y,r);i[p]=hd(x,o,_,b,m)}return i}};function hd(e,t,n,r,i){let a=1-e;return a*a*a*t+3*a*a*e*n+3*a*e*e*r+e*e*e*i}function gd(e,t,n,r,i){let a=1-e;return 3*a*a*(n-t)+6*a*e*(r-n)+3*e*e*(i-r)}function _d(e,t,n,r,i){let a=(e-t)/(i-t);for(let o=0;o<8;o++){let o=hd(a,t,n,r,i)-e;if(Math.abs(o)<1e-10)break;let s=gd(a,t,n,r,i);if(Math.abs(s)<1e-10)break;a=Math.max(0,Math.min(1,a-o/s))}return a}var vd=class{constructor(e,t,n,r){if(e===void 0)throw Error(`THREE.KeyframeTrack: track name is undefined`);if(t===void 0||t.length===0)throw Error(`THREE.KeyframeTrack: no keyframes in track named `+e);this.name=e,this.times=cd(t,this.TimeBufferType),this.values=cd(n,this.ValueBufferType),this.setInterpolation(r||this.DefaultInterpolation)}static toJSON(e){let t=e.constructor,n;if(t.toJSON!==this.toJSON)n=t.toJSON(e);else{n={name:e.name,times:cd(e.times,Array),values:cd(e.values,Array)};let t=e.getInterpolation();t!==e.DefaultInterpolation&&(n.interpolation=t),ld(e.settings)&&(n.settings={inTangents:cd(e.settings.inTangents,Array),outTangents:cd(e.settings.outTangents,Array)})}return n.type=e.ValueTypeName,n}InterpolantFactoryMethodDiscrete(e){return new pd(this.times,this.values,this.getValueSize(),e)}InterpolantFactoryMethodLinear(e){return new fd(this.times,this.values,this.getValueSize(),e)}InterpolantFactoryMethodSmooth(e){return new dd(this.times,this.values,this.getValueSize(),e)}InterpolantFactoryMethodBezier(e){let t=new md(this.times,this.values,this.getValueSize(),e);return this.settings&&(t.inTangents=this.settings.inTangents,t.outTangents=this.settings.outTangents),t}setInterpolation(e){let t;switch(e){case po:t=this.InterpolantFactoryMethodDiscrete;break;case mo:t=this.InterpolantFactoryMethodLinear;break;case ho:t=this.InterpolantFactoryMethodSmooth;break;case go:t=this.InterpolantFactoryMethodBezier}if(t===void 0){let t=`unsupported interpolation for `+this.ValueTypeName+` keyframe track named `+this.name;if(this.createInterpolant===void 0){if(e!==this.DefaultInterpolation)this.setInterpolation(this.DefaultInterpolation);else throw Error(t)}return K(`KeyframeTrack:`,t),this}return this.createInterpolant=t,this}getInterpolation(){switch(this.createInterpolant){case this.InterpolantFactoryMethodDiscrete:return po;case this.InterpolantFactoryMethodLinear:return mo;case this.InterpolantFactoryMethodSmooth:return ho;case this.InterpolantFactoryMethodBezier:return go}}getValueSize(){return this.values.length/this.times.length}shift(e){if(e!==0){let t=this.times;for(let n=0,r=t.length;n!==r;++n)t[n]+=e}return this}scale(e){if(e!==1){let t=this.times;for(let n=0,r=t.length;n!==r;++n)t[n]*=e;ld(this.settings)&&(yd(this.settings.inTangents,e),yd(this.settings.outTangents,e))}return this}trim(e,t){let n=this.times,r=n.length,i=0,a=r-1;for(;i!==r&&n[i]<e;)++i;for(;a!==-1&&n[a]>t;)--a;if(++a,i!==0||a!==r){i>=a&&(a=Math.max(a,1),i=a-1);let e=this.getValueSize();this.times=n.slice(i,a),this.values=this.values.slice(i*e,a*e)}return this}validate(){let e=!0,t=this.getValueSize();t-Math.floor(t)!==0&&(q(`KeyframeTrack: Invalid value size in track.`,this),e=!1);let n=this.times,r=this.values,i=n.length;i===0&&(q(`KeyframeTrack: Track is empty.`,this),e=!1);let a=null;for(let t=0;t!==i;t++){let r=n[t];if(typeof r==`number`&&isNaN(r)){q(`KeyframeTrack: Time is not a valid number.`,this,t,r),e=!1;break}if(a!==null&&a>r){q(`KeyframeTrack: Out of order keys.`,this,t,r,a),e=!1;break}a=r}if(r!==void 0&&ko(r))for(let t=0,n=r.length;t!==n;++t){let n=r[t];if(isNaN(n)){q(`KeyframeTrack: Value is not a valid number.`,this,t,n),e=!1;break}}return e}optimize(){let e=this.times.slice(),t=this.values.slice(),n=this.getValueSize(),r=this.getInterpolation()===ho,i=e.length-1,a=1;for(let o=1;o<i;++o){let i=!1,s=e[o];if(s!==e[o+1]&&(o!==1||s!==e[0])){if(r)i=!0;else{let e=o*n,r=e-n,a=e+n;for(let o=0;o!==n;++o){let n=t[e+o];if(n!==t[r+o]||n!==t[a+o]){i=!0;break}}}}if(i){if(o!==a){e[a]=e[o];let r=o*n,i=a*n;for(let e=0;e!==n;++e)t[i+e]=t[r+e]}++a}}if(i>0){e[a]=e[i];for(let e=i*n,r=a*n,o=0;o!==n;++o)t[r+o]=t[e+o];++a}return a===e.length?(this.times=e,this.values=t):(this.times=e.slice(0,a),this.values=t.slice(0,a*n)),this}clone(){let e=this.times.slice(),t=this.values.slice(),n=this.constructor,r=new n(this.name,e,t);return r.createInterpolant=this.createInterpolant,ld(this.settings)&&(r.settings={inTangents:this.settings.inTangents.slice(),outTangents:this.settings.outTangents.slice()}),r}};function yd(e,t){for(let n=0,r=e.length;n!==r;n+=2)e[n]*=t}vd.prototype.ValueTypeName=``,vd.prototype.TimeBufferType=Float32Array,vd.prototype.ValueBufferType=Float32Array,vd.prototype.DefaultInterpolation=mo;var bd=class extends vd{constructor(e,t,n){super(e,t,n)}};bd.prototype.ValueTypeName=`bool`,bd.prototype.ValueBufferType=Array,bd.prototype.DefaultInterpolation=po,bd.prototype.InterpolantFactoryMethodLinear=void 0,bd.prototype.InterpolantFactoryMethodSmooth=void 0;var xd=class extends vd{constructor(e,t,n,r){super(e,t,n,r)}};xd.prototype.ValueTypeName=`color`;var Sd=class extends vd{constructor(e,t,n,r){super(e,t,n,r)}};Sd.prototype.ValueTypeName=`number`;var Cd=class extends ud{constructor(e,t,n,r){super(e,t,n,r)}interpolate_(e,t,n,r){let i=this.resultBuffer,a=this.sampleValues,o=this.valueSize,s=(n-t)/(r-t),c=e*o;for(let e=c+o;c!==e;c+=4)ds.slerpFlat(i,0,a,c-o,a,c,s);return i}},wd=class extends vd{constructor(e,t,n,r){super(e,t,n,r)}InterpolantFactoryMethodLinear(e){return new Cd(this.times,this.values,this.getValueSize(),e)}};wd.prototype.ValueTypeName=`quaternion`,wd.prototype.InterpolantFactoryMethodSmooth=void 0;var Td=class extends vd{constructor(e,t,n){super(e,t,n)}};Td.prototype.ValueTypeName=`string`,Td.prototype.ValueBufferType=Array,Td.prototype.DefaultInterpolation=po,Td.prototype.InterpolantFactoryMethodLinear=void 0,Td.prototype.InterpolantFactoryMethodSmooth=void 0;var Ed=class extends vd{constructor(e,t,n,r){super(e,t,n,r)}};Ed.prototype.ValueTypeName=`vector`;var Dd=class extends sc{constructor(e,t=1){super(),this.isLight=!0,this.type=`Light`,this.color=new mc(e),this.intensity=t}copy(e,t){return super.copy(e,t),this.color.copy(e.color),this.intensity=e.intensity,this}toJSON(e){let t=super.toJSON(e);return t.object.color=this.color.getHex(),t.object.intensity=this.intensity,t}},Od=new Ps,kd=new X,Ad=new X,jd=class{constructor(e){this.camera=e,this.intensity=1,this.bias=0,this.biasNode=null,this.normalBias=0,this.radius=1,this.blurSamples=8,this.mapSize=new Y(512,512),this.mapType=sa,this.map=null,this.mapPass=null,this.matrix=new Ps,this.autoUpdate=!0,this.needsUpdate=!1,this._frustum=new Wl,this._frameExtents=new Y(1,1),this._viewportCount=1,this._viewports=[new ks(0,0,1,1)]}getViewportCount(){return this._viewportCount}getCamera(){return this.camera}getFrustum(){return this._frustum}updateMatrices(e){let t=this.camera;kd.setFromMatrixPosition(e.matrixWorld),t.position.copy(kd),Ad.setFromMatrixPosition(e.target.matrixWorld),t.lookAt(Ad),t.updateMatrixWorld(),this._updateMatrix(t,this.matrix,this._frustum)}_updateMatrix(e,t,n,r){Od.multiplyMatrices(e.projectionMatrix,e.matrixWorldInverse),n.setFromProjectionMatrix(Od,e.coordinateSystem,e.reversedDepth);let i=this._frameExtents,a=r?r.z/i.x:1,o=r?r.w/i.y:1,s=r?r.x/i.x:0,c=r?r.y/i.y:0;e.coordinateSystem===2001||e.reversedDepth?t.set(.5*a,0,0,.5*a+s,0,.5*o,0,.5*o+c,0,0,1,0,0,0,0,1):t.set(.5*a,0,0,.5*a+s,0,.5*o,0,.5*o+c,0,0,.5,.5,0,0,0,1),t.multiply(Od)}getViewport(e){return this._viewports[e]}getFrameExtents(){return this._frameExtents}dispose(){this.map&&this.map.dispose(),this.mapPass&&this.mapPass.dispose()}copy(e){return this.camera=e.camera.clone(),this.intensity=e.intensity,this.bias=e.bias,this.radius=e.radius,this.autoUpdate=e.autoUpdate,this.needsUpdate=e.needsUpdate,this.normalBias=e.normalBias,this.blurSamples=e.blurSamples,this.mapSize.copy(e.mapSize),this.biasNode=e.biasNode,this}clone(){return new this.constructor().copy(this)}toJSON(){let e={};return e.intensity=this.intensity,e.bias=this.bias,e.normalBias=this.normalBias,e.radius=this.radius,e.blurSamples=this.blurSamples,e.mapSize=this.mapSize.toArray(),e.camera=this.camera.toJSON(!1).object,delete e.camera.matrix,e}},Md=new X,Nd=new ds,Pd=new X,Fd=class extends sc{constructor(){super(),this.isCamera=!0,this.type=`Camera`,this.matrixWorldInverse=new Ps,this.projectionMatrix=new Ps,this.projectionMatrixInverse=new Ps,this.coordinateSystem=Do,this._reversedDepth=!1}get reversedDepth(){return this._reversedDepth}copy(e,t){return super.copy(e,t),this.matrixWorldInverse.copy(e.matrixWorldInverse),this.projectionMatrix.copy(e.projectionMatrix),this.projectionMatrixInverse.copy(e.projectionMatrixInverse),this.coordinateSystem=e.coordinateSystem,this}getWorldDirection(e){return super.getWorldDirection(e).negate()}updateMatrixWorld(e){super.updateMatrixWorld(e),this.matrixWorld.decompose(Md,Nd,Pd),Pd.x===1&&Pd.y===1&&Pd.z===1?this.matrixWorldInverse.copy(this.matrixWorld).invert():this.matrixWorldInverse.compose(Md,Nd,Pd.set(1,1,1)).invert()}updateWorldMatrix(e,t,n=!1){super.updateWorldMatrix(e,t,n),this.matrixWorld.decompose(Md,Nd,Pd),Pd.x===1&&Pd.y===1&&Pd.z===1?this.matrixWorldInverse.copy(this.matrixWorld).invert():this.matrixWorldInverse.compose(Md,Nd,Pd.set(1,1,1)).invert()}clone(){return new this.constructor().copy(this)}},Id=new X,Ld=new Y,Rd=new Y,zd=class extends Fd{constructor(e=50,t=1,n=.1,r=2e3){super(),this.isPerspectiveCamera=!0,this.type=`PerspectiveCamera`,this.fov=e,this.zoom=1,this.near=n,this.far=r,this.focus=10,this.aspect=t,this.view=null,this.filmGauge=35,this.filmOffset=0,this.updateProjectionMatrix()}copy(e,t){return super.copy(e,t),this.fov=e.fov,this.zoom=e.zoom,this.near=e.near,this.far=e.far,this.focus=e.focus,this.aspect=e.aspect,this.view=e.view===null?null:Object.assign({},e.view),this.filmGauge=e.filmGauge,this.filmOffset=e.filmOffset,this}setFocalLength(e){let t=.5*this.getFilmHeight()/e;this.fov=Ho*2*Math.atan(t),this.updateProjectionMatrix()}getFocalLength(){let e=Math.tan(Vo*.5*this.fov);return .5*this.getFilmHeight()/e}getEffectiveFOV(){return Ho*2*Math.atan(Math.tan(Vo*.5*this.fov)/this.zoom)}getFilmWidth(){return this.filmGauge*Math.min(this.aspect,1)}getFilmHeight(){return this.filmGauge/Math.max(this.aspect,1)}getViewBounds(e,t,n){Id.set(-1,-1,.5).applyMatrix4(this.projectionMatrixInverse),t.set(Id.x,Id.y).multiplyScalar(-e/Id.z),Id.set(1,1,.5).applyMatrix4(this.projectionMatrixInverse),n.set(Id.x,Id.y).multiplyScalar(-e/Id.z)}getViewSize(e,t){return this.getViewBounds(e,Ld,Rd),t.subVectors(Rd,Ld)}setViewOffset(e,t,n,r,i,a){this.aspect=e/t,this.view===null&&(this.view={enabled:!0,fullWidth:1,fullHeight:1,offsetX:0,offsetY:0,width:1,height:1}),this.view.enabled=!0,this.view.fullWidth=e,this.view.fullHeight=t,this.view.offsetX=n,this.view.offsetY=r,this.view.width=i,this.view.height=a,this.updateProjectionMatrix()}clearViewOffset(){this.view!==null&&(this.view.enabled=!1),this.updateProjectionMatrix()}updateProjectionMatrix(){let e=this.near,t=e*Math.tan(Vo*.5*this.fov)/this.zoom,n=2*t,r=this.aspect*n,i=-.5*r,a=this.view;if(this.view!==null&&this.view.enabled){let e=a.fullWidth,o=a.fullHeight;i+=a.offsetX*r/e,t-=a.offsetY*n/o,r*=a.width/e,n*=a.height/o}let o=this.filmOffset;o!==0&&(i+=e*o/this.getFilmWidth()),this.projectionMatrix.makePerspective(i,i+r,t,t-n,e,this.far,this.coordinateSystem,this.reversedDepth),this.projectionMatrixInverse.copy(this.projectionMatrix).invert()}toJSON(e){let t=super.toJSON(e);return t.object.fov=this.fov,t.object.zoom=this.zoom,t.object.near=this.near,t.object.far=this.far,t.object.focus=this.focus,t.object.aspect=this.aspect,this.view!==null&&(t.object.view=Object.assign({},this.view)),t.object.filmGauge=this.filmGauge,t.object.filmOffset=this.filmOffset,t}},Bd=class extends Fd{constructor(e=-1,t=1,n=1,r=-1,i=.1,a=2e3){super(),this.isOrthographicCamera=!0,this.type=`OrthographicCamera`,this.zoom=1,this.view=null,this.left=e,this.right=t,this.top=n,this.bottom=r,this.near=i,this.far=a,this.updateProjectionMatrix()}copy(e,t){return super.copy(e,t),this.left=e.left,this.right=e.right,this.top=e.top,this.bottom=e.bottom,this.near=e.near,this.far=e.far,this.zoom=e.zoom,this.view=e.view===null?null:Object.assign({},e.view),this}setViewOffset(e,t,n,r,i,a){this.view===null&&(this.view={enabled:!0,fullWidth:1,fullHeight:1,offsetX:0,offsetY:0,width:1,height:1}),this.view.enabled=!0,this.view.fullWidth=e,this.view.fullHeight=t,this.view.offsetX=n,this.view.offsetY=r,this.view.width=i,this.view.height=a,this.updateProjectionMatrix()}clearViewOffset(){this.view!==null&&(this.view.enabled=!1),this.updateProjectionMatrix()}updateProjectionMatrix(){let e=(this.right-this.left)/(2*this.zoom),t=(this.top-this.bottom)/(2*this.zoom),n=(this.right+this.left)/2,r=(this.top+this.bottom)/2,i=n-e,a=n+e,o=r+t,s=r-t;if(this.view!==null&&this.view.enabled){let e=(this.right-this.left)/this.view.fullWidth/this.zoom,t=(this.top-this.bottom)/this.view.fullHeight/this.zoom;i+=e*this.view.offsetX,a=i+e*this.view.width,o-=t*this.view.offsetY,s=o-t*this.view.height}this.projectionMatrix.makeOrthographic(i,a,o,s,this.near,this.far,this.coordinateSystem,this.reversedDepth),this.projectionMatrixInverse.copy(this.projectionMatrix).invert()}toJSON(e){let t=super.toJSON(e);return t.object.zoom=this.zoom,t.object.left=this.left,t.object.right=this.right,t.object.top=this.top,t.object.bottom=this.bottom,t.object.near=this.near,t.object.far=this.far,this.view!==null&&(t.object.view=Object.assign({},this.view)),t}},Vd=class extends jd{constructor(){super(new Bd(-5,5,5,-5,.5,500)),this.isDirectionalLightShadow=!0}},Hd=class extends Dd{constructor(e,t){super(e,t),this.isDirectionalLight=!0,this.type=`DirectionalLight`,this.position.copy(sc.DEFAULT_UP),this.updateMatrix(),this.target=new sc,this.shadow=new Vd}dispose(){super.dispose(),this.shadow.dispose()}copy(e){return super.copy(e),this.target=e.target.clone(),this.shadow=e.shadow.clone(),this}toJSON(e){let t=super.toJSON(e);return t.object.shadow=this.shadow.toJSON(),t.object.target=this.target.uuid,t}},Ud=class extends Dd{constructor(e,t){super(e,t),this.isAmbientLight=!0,this.type=`AmbientLight`}},Wd=class extends ul{constructor(){super(),this.isInstancedBufferGeometry=!0,this.type=`InstancedBufferGeometry`,this.instanceCount=1/0}copy(e){return super.copy(e),this.instanceCount=e.instanceCount,this}toJSON(){let e=super.toJSON();return e.instanceCount=this.instanceCount,e.isInstancedBufferGeometry=!0,e}},Gd=-90,Kd=1,qd=class extends sc{constructor(e,t,n){super(),this.type=`CubeCamera`,this.renderTarget=n,this.coordinateSystem=null,this.activeMipmapLevel=0;let r=new zd(Gd,Kd,e,t);r.layers=this.layers,this.add(r);let i=new zd(Gd,Kd,e,t);i.layers=this.layers,this.add(i);let a=new zd(Gd,Kd,e,t);a.layers=this.layers,this.add(a);let o=new zd(Gd,Kd,e,t);o.layers=this.layers,this.add(o);let s=new zd(Gd,Kd,e,t);s.layers=this.layers,this.add(s);let c=new zd(Gd,Kd,e,t);c.layers=this.layers,this.add(c)}updateCoordinateSystem(){let e=this.coordinateSystem,t=this.children.concat(),[n,r,i,a,o,s]=t;for(let e of t)this.remove(e);if(e===2e3)n.up.set(0,1,0),n.lookAt(1,0,0),r.up.set(0,1,0),r.lookAt(-1,0,0),i.up.set(0,0,-1),i.lookAt(0,1,0),a.up.set(0,0,1),a.lookAt(0,-1,0),o.up.set(0,1,0),o.lookAt(0,0,1),s.up.set(0,1,0),s.lookAt(0,0,-1);else if(e===2001)n.up.set(0,-1,0),n.lookAt(-1,0,0),r.up.set(0,-1,0),r.lookAt(1,0,0),i.up.set(0,0,1),i.lookAt(0,1,0),a.up.set(0,0,-1),a.lookAt(0,-1,0),o.up.set(0,-1,0),o.lookAt(0,0,1),s.up.set(0,-1,0),s.lookAt(0,0,-1);else throw Error(`THREE.CubeCamera.updateCoordinateSystem(): Invalid coordinate system: `+e);for(let e of t)this.add(e),e.updateMatrixWorld()}update(e,t){this.parent===null&&this.updateMatrixWorld();let{renderTarget:n,activeMipmapLevel:r}=this;this.coordinateSystem!==e.coordinateSystem&&(this.coordinateSystem=e.coordinateSystem,this.updateCoordinateSystem());let[i,a,o,s,c,l]=this.children,u=e.getRenderTarget(),d=e.getActiveCubeFace(),f=e.getActiveMipmapLevel(),p=e.xr.enabled;e.xr.enabled=!1;let m=n.texture.generateMipmaps;n.texture.generateMipmaps=!1;let h=!1;h=e.isWebGLRenderer===!0?e.state.buffers.depth.getReversed():e.reversedDepthBuffer,e.setRenderTarget(n,0,r),h&&e.autoClear===!1&&e.clearDepth(),e.render(t,i),e.setRenderTarget(n,1,r),h&&e.autoClear===!1&&e.clearDepth(),e.render(t,a),e.setRenderTarget(n,2,r),h&&e.autoClear===!1&&e.clearDepth(),e.render(t,o),e.setRenderTarget(n,3,r),h&&e.autoClear===!1&&e.clearDepth(),e.render(t,s),e.setRenderTarget(n,4,r),h&&e.autoClear===!1&&e.clearDepth(),e.render(t,c),n.texture.generateMipmaps=m,e.setRenderTarget(n,5,r),h&&e.autoClear===!1&&e.clearDepth(),e.render(t,l),e.setRenderTarget(u,d,f),e.xr.enabled=p,n.texture.needsPMREMUpdate=!0}},Jd=class extends zd{constructor(e=[]){super(),this.isArrayCamera=!0,this.isMultiViewCamera=!1,this.cameras=e}},Yd=`\\[\\]\\.:\\/`,Xd=RegExp(`[\\[\\]\\.:\\/]`,`g`),Zd=`[^\\[\\]\\.:\\/]`,Qd=`[^`+Yd.replace(`\\.`,``)+`]`,$d=`((?:WC+[\\/:])*)`.replace(`WC`,Zd),ef=`(WCOD+)?`.replace(`WCOD`,Qd),tf=`(?:\\.(WC+)(?:\\[(.+)\\])?)?`.replace(`WC`,Zd),nf=`\\.(WC+)(?:\\[(.+)\\])?`.replace(`WC`,Zd),rf=RegExp(`^`+$d+ef+tf+nf+`$`),af=[`material`,`materials`,`bones`,`map`],of=class{constructor(e,t,n){let r=n||sf.parseTrackName(t);this._targetGroup=e,this._bindings=e.subscribe_(t,r)}getValue(e,t){this.bind();let n=this._targetGroup.nCachedObjects_,r=this._bindings[n];r!==void 0&&r.getValue(e,t)}setValue(e,t){let n=this._bindings;for(let r=this._targetGroup.nCachedObjects_,i=n.length;r!==i;++r)n[r].setValue(e,t)}bind(){let e=this._bindings;for(let t=this._targetGroup.nCachedObjects_,n=e.length;t!==n;++t)e[t].bind()}unbind(){let e=this._bindings;for(let t=this._targetGroup.nCachedObjects_,n=e.length;t!==n;++t)e[t].unbind()}},sf=class e{constructor(t,n,r){this.path=n,this.parsedPath=r||e.parseTrackName(n),this.node=e.findNode(t,this.parsedPath.nodeName),this.rootNode=t,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}static create(t,n,r){return t&&t.isAnimationObjectGroup?new e.Composite(t,n,r):new e(t,n,r)}static sanitizeNodeName(e){return e.replace(/\s/g,`_`).replace(Xd,``)}static parseTrackName(e){let t=rf.exec(e);if(t===null)throw Error(`THREE.PropertyBinding: Cannot parse trackName: `+e);let n={nodeName:t[2],objectName:t[3],objectIndex:t[4],propertyName:t[5],propertyIndex:t[6]},r=n.nodeName&&n.nodeName.lastIndexOf(`.`);if(r!==void 0&&r!==-1){let e=n.nodeName.substring(r+1);af.indexOf(e)!==-1&&(n.nodeName=n.nodeName.substring(0,r),n.objectName=e)}if(n.propertyName===null||n.propertyName.length===0)throw Error(`THREE.PropertyBinding: can not parse propertyName from trackName: `+e);return n}static findNode(e,t){if(t===void 0||t===``||t===`.`||t===-1||t===e.name||t===e.uuid)return e;if(e.skeleton){let n=e.skeleton.getBoneByName(t);if(n!==void 0)return n}if(e.children){let n=function(e){for(let r=0;r<e.length;r++){let i=e[r];if(i.name===t||i.uuid===t)return i;let a=n(i.children);if(a)return a}return null},r=n(e.children);if(r)return r}return null}_getValue_unavailable(){}_setValue_unavailable(){}_getValue_direct(e,t){e[t]=this.targetObject[this.propertyName]}_getValue_array(e,t){let n=this.resolvedProperty;for(let r=0,i=n.length;r!==i;++r)e[t++]=n[r]}_getValue_arrayElement(e,t){e[t]=this.resolvedProperty[this.propertyIndex]}_getValue_toArray(e,t){this.resolvedProperty.toArray(e,t)}_setValue_direct(e,t){this.targetObject[this.propertyName]=e[t]}_setValue_direct_setNeedsUpdate(e,t){this.targetObject[this.propertyName]=e[t],this.targetObject.needsUpdate=!0}_setValue_direct_setMatrixWorldNeedsUpdate(e,t){this.targetObject[this.propertyName]=e[t],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_array(e,t){let n=this.resolvedProperty;for(let r=0,i=n.length;r!==i;++r)n[r]=e[t++]}_setValue_array_setNeedsUpdate(e,t){let n=this.resolvedProperty;for(let r=0,i=n.length;r!==i;++r)n[r]=e[t++];this.targetObject.needsUpdate=!0}_setValue_array_setMatrixWorldNeedsUpdate(e,t){let n=this.resolvedProperty;for(let r=0,i=n.length;r!==i;++r)n[r]=e[t++];this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_arrayElement(e,t){this.resolvedProperty[this.propertyIndex]=e[t]}_setValue_arrayElement_setNeedsUpdate(e,t){this.resolvedProperty[this.propertyIndex]=e[t],this.targetObject.needsUpdate=!0}_setValue_arrayElement_setMatrixWorldNeedsUpdate(e,t){this.resolvedProperty[this.propertyIndex]=e[t],this.targetObject.matrixWorldNeedsUpdate=!0}_setValue_fromArray(e,t){this.resolvedProperty.fromArray(e,t)}_setValue_fromArray_setNeedsUpdate(e,t){this.resolvedProperty.fromArray(e,t),this.targetObject.needsUpdate=!0}_setValue_fromArray_setMatrixWorldNeedsUpdate(e,t){this.resolvedProperty.fromArray(e,t),this.targetObject.matrixWorldNeedsUpdate=!0}_getValue_unbound(e,t){this.bind(),this.getValue(e,t)}_setValue_unbound(e,t){this.bind(),this.setValue(e,t)}bind(){let t=this.node,n=this.parsedPath,r=n.objectName,i=n.propertyName,a=n.propertyIndex;if(t||(t=e.findNode(this.rootNode,n.nodeName),this.node=t),this.getValue=this._getValue_unavailable,this.setValue=this._setValue_unavailable,!t){K(`PropertyBinding: No target node found for track: `+this.path+`.`);return}if(r){let e=n.objectIndex;switch(r){case`materials`:if(!t.material){q(`PropertyBinding: Can not bind to material as node does not have a material.`,this);return}if(!t.material.materials){q(`PropertyBinding: Can not bind to material.materials as node.material does not have a materials array.`,this);return}t=t.material.materials;break;case`bones`:if(!t.skeleton){q(`PropertyBinding: Can not bind to bones as node does not have a skeleton.`,this);return}t=t.skeleton.bones;for(let n=0;n<t.length;n++)if(t[n].name===e){e=n;break}break;case`map`:if(`map`in t){t=t.map;break}if(!t.material){q(`PropertyBinding: Can not bind to material as node does not have a material.`,this);return}if(!t.material.map){q(`PropertyBinding: Can not bind to material.map as node.material does not have a map.`,this);return}t=t.material.map;break;default:if(t[r]===void 0){q(`PropertyBinding: Can not bind to objectName of node undefined.`,this);return}t=t[r]}if(e!==void 0){if(t[e]===void 0){q(`PropertyBinding: Trying to bind to objectIndex of objectName, but is undefined.`,this,t);return}t=t[e]}}let o=t[i];if(o===void 0){let e=n.nodeName;q(`PropertyBinding: Trying to update property for track: `+e+`.`+i+` but it wasn't found.`,t);return}let s=this.Versioning.None;this.targetObject=t,t.isMaterial===!0?s=this.Versioning.NeedsUpdate:t.isObject3D===!0&&(s=this.Versioning.MatrixWorldNeedsUpdate);let c=this.BindingType.Direct;if(a!==void 0){if(i===`morphTargetInfluences`){if(!t.geometry){q(`PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.`,this);return}if(!t.geometry.morphAttributes){q(`PropertyBinding: Can not bind to morphTargetInfluences because node does not have a geometry.morphAttributes.`,this);return}t.morphTargetDictionary[a]!==void 0&&(a=t.morphTargetDictionary[a])}c=this.BindingType.ArrayElement,this.resolvedProperty=o,this.propertyIndex=a}else o.fromArray!==void 0&&o.toArray!==void 0?(c=this.BindingType.HasFromToArray,this.resolvedProperty=o):Array.isArray(o)?(c=this.BindingType.EntireArray,this.resolvedProperty=o):this.propertyName=i;this.getValue=this.GetterByBindingType[c],this.setValue=this.SetterByBindingTypeAndVersioning[c][s]}unbind(){this.node=null,this.getValue=this._getValue_unbound,this.setValue=this._setValue_unbound}};sf.Composite=of,sf.prototype.BindingType={Direct:0,EntireArray:1,ArrayElement:2,HasFromToArray:3},sf.prototype.Versioning={None:0,NeedsUpdate:1,MatrixWorldNeedsUpdate:2},sf.prototype.GetterByBindingType=[sf.prototype._getValue_direct,sf.prototype._getValue_array,sf.prototype._getValue_arrayElement,sf.prototype._getValue_toArray],sf.prototype.SetterByBindingTypeAndVersioning=[[sf.prototype._setValue_direct,sf.prototype._setValue_direct_setNeedsUpdate,sf.prototype._setValue_direct_setMatrixWorldNeedsUpdate],[sf.prototype._setValue_array,sf.prototype._setValue_array_setNeedsUpdate,sf.prototype._setValue_array_setMatrixWorldNeedsUpdate],[sf.prototype._setValue_arrayElement,sf.prototype._setValue_arrayElement_setNeedsUpdate,sf.prototype._setValue_arrayElement_setMatrixWorldNeedsUpdate],[sf.prototype._setValue_fromArray,sf.prototype._setValue_fromArray_setNeedsUpdate,sf.prototype._setValue_fromArray_setMatrixWorldNeedsUpdate]];var cf=class extends dl{constructor(e,t,n=1){super(e,t),this.isInstancedInterleavedBuffer=!0,this.meshPerAttribute=n}copy(e){return super.copy(e),this.meshPerAttribute=e.meshPerAttribute,this}clone(e){let t=super.clone(e);return t.meshPerAttribute=this.meshPerAttribute,t}toJSON(e){let t=super.toJSON(e);return t.isInstancedInterleavedBuffer=!0,t.meshPerAttribute=this.meshPerAttribute,t}},lf=new Ps,uf=class{constructor(e,t,n=0,r=1/0){this.ray=new wl(e,t),this.near=n,this.far=r,this.camera=null,this.layers=new Gs,this.params={Mesh:{},Line:{threshold:1},LOD:{},Points:{threshold:1},Sprite:{}}}set(e,t){this.ray.set(e,t)}setFromCamera(e,t){t.isPerspectiveCamera?(this.ray.origin.setFromMatrixPosition(t.matrixWorld),this.ray.direction.set(e.x,e.y,.5).unproject(t).sub(this.ray.origin).normalize(),this.camera=t):t.isOrthographicCamera?(this.ray.origin.set(e.x,e.y,t.projectionMatrix.elements[14]).unproject(t),this.ray.direction.set(0,0,-1).transformDirection(t.matrixWorld),this.camera=t):q(`Raycaster: Unsupported camera type: `+t.type)}setFromXRController(e){return lf.identity().extractRotation(e.matrixWorld),this.ray.origin.setFromMatrixPosition(e.matrixWorld),this.ray.direction.set(0,0,-1).applyMatrix4(lf),this}intersectObject(e,t=!0,n=[]){return ff(e,this,n,t),n.sort(df),n}intersectObjects(e,t=!0,n=[]){for(let r=0,i=e.length;r<i;r++)ff(e[r],this,n,t);return n.sort(df),n}};function df(e,t){return e.distance-t.distance}function ff(e,t,n,r){let i=!0;if(e.layers.test(t.layers)&&e.raycast(t,n)===!1&&(i=!1),i===!0&&r===!0){let r=e.children;for(let e=0,i=r.length;e<i;e++)ff(r[e],t,n,!0)}}(class e{static{e.prototype.isMatrix2=!0}constructor(e,t,n,r){this.elements=[1,0,0,1],e!==void 0&&this.set(e,t,n,r)}identity(){return this.set(1,0,0,1),this}fromArray(e,t=0){for(let n=0;n<4;n++)this.elements[n]=e[n+t];return this}set(e,t,n,r){let i=this.elements;return i[0]=e,i[2]=t,i[1]=n,i[3]=r,this}});var pf=new X,mf=new X,hf=new X,gf=new X,_f=new X,vf=new X,yf=new X,bf=class{constructor(e=new X,t=new X){this.start=e,this.end=t}set(e,t){return this.start.copy(e),this.end.copy(t),this}copy(e){return this.start.copy(e.start),this.end.copy(e.end),this}getCenter(e){return e.addVectors(this.start,this.end).multiplyScalar(.5)}delta(e){return e.subVectors(this.end,this.start)}distanceSq(){return this.start.distanceToSquared(this.end)}distance(){return this.start.distanceTo(this.end)}at(e,t){return this.delta(t).multiplyScalar(e).add(this.start)}closestPointToPointParameter(e,t){pf.subVectors(e,this.start),mf.subVectors(this.end,this.start);let n=mf.dot(mf);if(n===0)return 0;let r=mf.dot(pf)/n;return t&&(r=J(r,0,1)),r}closestPointToPoint(e,t,n){let r=this.closestPointToPointParameter(e,t);return this.delta(n).multiplyScalar(r).add(this.start)}distanceSqToLine3(e,t=vf,n=yf){let r=1e-8*1e-8,i,a,o=this.start,s=e.start,c=this.end,l=e.end;hf.subVectors(c,o),gf.subVectors(l,s),_f.subVectors(o,s);let u=hf.dot(hf),d=gf.dot(gf),f=gf.dot(_f);if(u<=r&&d<=r)return t.copy(o),n.copy(s),t.sub(n),t.dot(t);if(u<=r)i=0,a=f/d,a=J(a,0,1);else{let e=hf.dot(_f);if(d<=r)a=0,i=J(-e/u,0,1);else{let t=hf.dot(gf),n=u*d-t*t;i=n===0?0:J((t*f-e*d)/n,0,1),a=(t*i+f)/d,a<0?(a=0,i=J(-e/u,0,1)):a>1&&(a=1,i=J((t-e)/u,0,1))}}return t.copy(o).addScaledVector(hf,i),n.copy(s).addScaledVector(gf,a),t.distanceToSquared(n)}applyMatrix4(e){return this.start.applyMatrix4(e),this.end.applyMatrix4(e),this}equals(e){return e.start.equals(this.start)&&e.end.equals(this.end)}clone(){return new this.constructor().copy(this)}},xf=class extends ru{constructor(e,t=16776960){let n=new Uint16Array([0,1,1,2,2,3,3,0,4,5,5,6,6,7,7,4,0,4,1,5,2,6,3,7]),r=[1,1,1,-1,1,1,-1,-1,1,1,-1,1,1,1,-1,-1,1,-1,-1,-1,-1,1,-1,-1],i=new ul;i.setIndex(new Yc(n,1)),i.setAttribute(`position`,new Qc(r,3)),super(i,new Gl({color:t,toneMapped:!1})),this.box=e,this.type=`Box3Helper`,this.geometry.computeBoundingSphere()}updateMatrixWorld(e){let t=this.box;t.isEmpty()||(t.getCenter(this.position),t.getSize(this.scale),this.scale.multiplyScalar(.5),super.updateMatrixWorld(e))}dispose(){super.dispose(),this.geometry.dispose(),this.material.dispose()}},Sf=class extends Ro{constructor(e,t=null){super(),this.object=e,this.domElement=t,this.enabled=!0,this.state=-1,this.keys={},this.mouseButtons={LEFT:null,MIDDLE:null,RIGHT:null},this.touches={ONE:null,TWO:null}}connect(e){this.domElement!==null&&this.disconnect(),this.domElement=e}disconnect(){}dispose(){}update(){}};function Cf(e,t,n,r){let i=wf(r);switch(n){case ba:return e*t;case Ta:return e*t/i.components*i.byteLength;case Ea:return e*t/i.components*i.byteLength;case Da:return e*t*2/i.components*i.byteLength;case Oa:return e*t*2/i.components*i.byteLength;case xa:return e*t*3/i.components*i.byteLength;case Sa:return e*t*4/i.components*i.byteLength;case ka:return e*t*4/i.components*i.byteLength;case Aa:case ja:return Math.floor((e+3)/4)*Math.floor((t+3)/4)*8;case Ma:case Na:return Math.floor((e+3)/4)*Math.floor((t+3)/4)*16;case Fa:case La:return Math.max(e,16)*Math.max(t,8)/4;case Pa:case Ia:return Math.max(e,8)*Math.max(t,8)/2;case Ra:case za:case Va:case Ha:return Math.floor((e+3)/4)*Math.floor((t+3)/4)*8;case Ba:case Ua:case Wa:return Math.floor((e+3)/4)*Math.floor((t+3)/4)*16;case Ga:return Math.floor((e+3)/4)*Math.floor((t+3)/4)*16;case Ka:return Math.floor((e+4)/5)*Math.floor((t+3)/4)*16;case qa:return Math.floor((e+4)/5)*Math.floor((t+4)/5)*16;case Ja:return Math.floor((e+5)/6)*Math.floor((t+4)/5)*16;case Ya:return Math.floor((e+5)/6)*Math.floor((t+5)/6)*16;case Xa:return Math.floor((e+7)/8)*Math.floor((t+4)/5)*16;case Za:return Math.floor((e+7)/8)*Math.floor((t+5)/6)*16;case Qa:return Math.floor((e+7)/8)*Math.floor((t+7)/8)*16;case $a:return Math.floor((e+9)/10)*Math.floor((t+4)/5)*16;case eo:return Math.floor((e+9)/10)*Math.floor((t+5)/6)*16;case to:return Math.floor((e+9)/10)*Math.floor((t+7)/8)*16;case no:return Math.floor((e+9)/10)*Math.floor((t+9)/10)*16;case ro:return Math.floor((e+11)/12)*Math.floor((t+9)/10)*16;case io:return Math.floor((e+11)/12)*Math.floor((t+11)/12)*16;case ao:case oo:case so:return Math.ceil(e/4)*Math.ceil(t/4)*16;case co:case lo:return Math.ceil(e/4)*Math.ceil(t/4)*8;case uo:case fo:return Math.ceil(e/4)*Math.ceil(t/4)*16}throw Error(`Unable to determine texture byte length for ${n} format.`)}function wf(e){switch(e){case sa:case ca:return{byteLength:1,components:1};case ua:case la:case ma:return{byteLength:2,components:1};case ha:case ga:return{byteLength:2,components:4};case fa:case da:case pa:return{byteLength:4,components:1};case va:case ya:return{byteLength:4,components:3}}throw Error(`THREE.TextureUtils: Unknown texture type ${e}.`)}typeof __THREE_DEVTOOLS__<`u`&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent(`register`,{detail:{revision:`186`}})),typeof window<`u`&&(window.__THREE__?K(`WARNING: Multiple instances of Three.js being imported.`):window.__THREE__=`186`);function Tf(){let e=null,t=!1,n=null,r=null;function i(t,a){r=e.requestAnimationFrame(i),n(t,a)}return{start:function(){t!==!0&&n!==null&&e!==null&&(r=e.requestAnimationFrame(i),t=!0)},stop:function(){e!==null&&e.cancelAnimationFrame(r),t=!1},setAnimationLoop:function(e){n=e},setContext:function(t){e=t}}}function Ef(e){let t=new WeakMap;function n(t,n){let r=t.array,i=t.usage,a=r.byteLength,o=e.createBuffer();e.bindBuffer(n,o),e.bufferData(n,r,i),t.onUploadCallback();let s;if(r instanceof Float32Array)s=e.FLOAT;else if(typeof Float16Array<`u`&&r instanceof Float16Array)s=e.HALF_FLOAT;else if(r instanceof Uint16Array)s=t.isFloat16BufferAttribute?e.HALF_FLOAT:e.UNSIGNED_SHORT;else if(r instanceof Int16Array)s=e.SHORT;else if(r instanceof Uint32Array)s=e.UNSIGNED_INT;else if(r instanceof Int32Array)s=e.INT;else if(r instanceof Int8Array)s=e.BYTE;else if(r instanceof Uint8Array)s=e.UNSIGNED_BYTE;else if(r instanceof Uint8ClampedArray)s=e.UNSIGNED_BYTE;else throw Error(`THREE.WebGLAttributes: Unsupported buffer data format: `+r);return{buffer:o,type:s,bytesPerElement:r.BYTES_PER_ELEMENT,version:t.version,size:a}}function r(t,n,r){let i=n.array,a=n.updateRanges;if(e.bindBuffer(r,t),a.length===0)e.bufferSubData(r,0,i);else{a.sort((e,t)=>e.start-t.start);let t=0;for(let e=1;e<a.length;e++){let n=a[t],r=a[e];r.start<=n.start+n.count+1?n.count=Math.max(n.count,r.start+r.count-n.start):(++t,a[t]=r)}a.length=t+1;for(let t=0,n=a.length;t<n;t++){let n=a[t];e.bufferSubData(r,n.start*i.BYTES_PER_ELEMENT,i,n.start,n.count)}n.clearUpdateRanges()}n.onUploadCallback()}function i(e){return e.isInterleavedBufferAttribute&&(e=e.data),t.get(e)}function a(n){n.isInterleavedBufferAttribute&&(n=n.data);let r=t.get(n);r&&(e.deleteBuffer(r.buffer),t.delete(n))}function o(e,i){if(e.isInterleavedBufferAttribute&&(e=e.data),e.isGLBufferAttribute){let n=t.get(e);(!n||n.version<e.version)&&t.set(e,{buffer:e.buffer,type:e.type,bytesPerElement:e.elementSize,version:e.version});return}let a=t.get(e);if(a===void 0)t.set(e,n(e,i));else if(a.version<e.version){if(a.size!==e.array.byteLength)throw Error(`THREE.WebGLAttributes: The size of the buffer attribute's array buffer does not match the original size. Resizing buffer attributes is not supported.`);r(a.buffer,e,i),a.version=e.version}}return{get:i,remove:a,update:o}}var Df={alphahash_fragment:`#ifdef USE_ALPHAHASH
	if ( diffuseColor.a < getAlphaHashThreshold( vPosition ) ) discard;
#endif`,alphahash_pars_fragment:`#ifdef USE_ALPHAHASH
	const float ALPHA_HASH_SCALE = 0.05;
	float hash2D( vec2 value ) {
		return fract( 1.0e4 * sin( 17.0 * value.x + 0.1 * value.y ) * ( 0.1 + abs( sin( 13.0 * value.y + value.x ) ) ) );
	}
	float hash3D( vec3 value ) {
		return hash2D( vec2( hash2D( value.xy ), value.z ) );
	}
	float getAlphaHashThreshold( vec3 position ) {
		float maxDeriv = max(
			length( dFdx( position.xyz ) ),
			length( dFdy( position.xyz ) )
		);
		float pixScale = 1.0 / ( ALPHA_HASH_SCALE * maxDeriv );
		vec2 pixScales = vec2(
			exp2( floor( log2( pixScale ) ) ),
			exp2( ceil( log2( pixScale ) ) )
		);
		vec2 alpha = vec2(
			hash3D( floor( pixScales.x * position.xyz ) ),
			hash3D( floor( pixScales.y * position.xyz ) )
		);
		float lerpFactor = fract( log2( pixScale ) );
		float x = ( 1.0 - lerpFactor ) * alpha.x + lerpFactor * alpha.y;
		float a = min( lerpFactor, 1.0 - lerpFactor );
		vec3 cases = vec3(
			x * x / ( 2.0 * a * ( 1.0 - a ) ),
			( x - 0.5 * a ) / ( 1.0 - a ),
			1.0 - ( ( 1.0 - x ) * ( 1.0 - x ) / ( 2.0 * a * ( 1.0 - a ) ) )
		);
		float threshold = ( x < ( 1.0 - a ) )
			? ( ( x < a ) ? cases.x : cases.y )
			: cases.z;
		return clamp( threshold , 1.0e-6, 1.0 );
	}
#endif`,alphamap_fragment:`#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, vAlphaMapUv ).g;
#endif`,alphamap_pars_fragment:`#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,alphatest_fragment:`#ifdef USE_ALPHATEST
	#ifdef ALPHA_TO_COVERAGE
	diffuseColor.a = smoothstep( alphaTest, alphaTest + fwidth( diffuseColor.a ), diffuseColor.a );
	if ( diffuseColor.a == 0.0 ) discard;
	#else
	if ( diffuseColor.a < alphaTest ) discard;
	#endif
#endif`,alphatest_pars_fragment:`#ifdef USE_ALPHATEST
	uniform float alphaTest;
#endif`,aomap_fragment:`#ifdef USE_AOMAP
	float ambientOcclusion = ( texture2D( aoMap, vAoMapUv ).r - 1.0 ) * aoMapIntensity + 1.0;
	reflectedLight.indirectDiffuse *= ambientOcclusion;
	#if defined( USE_CLEARCOAT ) 
		clearcoatSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_SHEEN ) 
		sheenSpecularIndirect *= ambientOcclusion;
	#endif
	#if defined( USE_ENVMAP ) && defined( STANDARD )
		float dotNV = saturate( dot( geometryNormal, geometryViewDir ) );
		reflectedLight.indirectSpecular *= computeSpecularOcclusion( dotNV, ambientOcclusion, material.roughness );
	#endif
#endif`,aomap_pars_fragment:`#ifdef USE_AOMAP
	uniform sampler2D aoMap;
	uniform float aoMapIntensity;
#endif`,batching_pars_vertex:`#ifdef USE_BATCHING
	#if ! defined( GL_ANGLE_multi_draw )
	#define gl_DrawID _gl_DrawID
	uniform int _gl_DrawID;
	#endif
	uniform highp sampler2D batchingTexture;
	uniform highp usampler2D batchingIdTexture;
	mat4 getBatchingMatrix( const in float i ) {
		int size = textureSize( batchingTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( batchingTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( batchingTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( batchingTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( batchingTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
	float getIndirectIndex( const in int i ) {
		int size = textureSize( batchingIdTexture, 0 ).x;
		int x = i % size;
		int y = i / size;
		return float( texelFetch( batchingIdTexture, ivec2( x, y ), 0 ).r );
	}
#endif
#ifdef USE_BATCHING_COLOR
	uniform sampler2D batchingColorTexture;
	vec4 getBatchingColor( const in float i ) {
		int size = textureSize( batchingColorTexture, 0 ).x;
		int j = int( i );
		int x = j % size;
		int y = j / size;
		return texelFetch( batchingColorTexture, ivec2( x, y ), 0 );
	}
#endif`,batching_vertex:`#ifdef USE_BATCHING
	mat4 batchingMatrix = getBatchingMatrix( getIndirectIndex( gl_DrawID ) );
#endif`,begin_vertex:`vec3 transformed = vec3( position );
#ifdef USE_ALPHAHASH
	vPosition = vec3( position );
#endif`,beginnormal_vertex:`vec3 objectNormal = vec3( normal );
#ifdef USE_TANGENT
	vec3 objectTangent = vec3( tangent.xyz );
#endif`,bsdfs:`float G_BlinnPhong_Implicit( ) {
	return 0.25;
}
float D_BlinnPhong( const in float shininess, const in float dotNH ) {
	return RECIPROCAL_PI * ( shininess * 0.5 + 1.0 ) * pow( dotNH, shininess );
}
vec3 BRDF_BlinnPhong( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in vec3 specularColor, const in float shininess ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( specularColor, 1.0, dotVH );
	float G = G_BlinnPhong_Implicit( );
	float D = D_BlinnPhong( shininess, dotNH );
	return F * ( G * D );
} // validated`,iridescence_fragment:`#ifdef USE_IRIDESCENCE
	const mat3 XYZ_TO_REC709 = mat3(
		 3.2404542, -0.9692660,  0.0556434,
		-1.5371385,  1.8760108, -0.2040259,
		-0.4985314,  0.0415560,  1.0572252
	);
	vec3 Fresnel0ToIor( vec3 fresnel0 ) {
		vec3 sqrtF0 = sqrt( fresnel0 );
		return ( vec3( 1.0 ) + sqrtF0 ) / ( vec3( 1.0 ) - sqrtF0 );
	}
	vec3 IorToFresnel0( vec3 transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - vec3( incidentIor ) ) / ( transmittedIor + vec3( incidentIor ) ) );
	}
	float IorToFresnel0( float transmittedIor, float incidentIor ) {
		return pow2( ( transmittedIor - incidentIor ) / ( transmittedIor + incidentIor ));
	}
	vec3 evalSensitivity( float OPD, vec3 shift ) {
		float phase = 2.0 * PI * OPD * 1.0e-9;
		vec3 val = vec3( 5.4856e-13, 4.4201e-13, 5.2481e-13 );
		vec3 pos = vec3( 1.6810e+06, 1.7953e+06, 2.2084e+06 );
		vec3 var = vec3( 4.3278e+09, 9.3046e+09, 6.6121e+09 );
		vec3 xyz = val * sqrt( 2.0 * PI * var ) * cos( pos * phase + shift ) * exp( - pow2( phase ) * var );
		xyz.x += 9.7470e-14 * sqrt( 2.0 * PI * 4.5282e+09 ) * cos( 2.2399e+06 * phase + shift[ 0 ] ) * exp( - 4.5282e+09 * pow2( phase ) );
		xyz /= 1.0685e-7;
		vec3 rgb = XYZ_TO_REC709 * xyz;
		return rgb;
	}
	vec3 evalIridescence( float outsideIOR, float eta2, float cosTheta1, float thinFilmThickness, vec3 baseF0 ) {
		vec3 I;
		float iridescenceIOR = mix( outsideIOR, eta2, smoothstep( 0.0, 0.03, thinFilmThickness ) );
		float sinTheta2Sq = pow2( outsideIOR / iridescenceIOR ) * ( 1.0 - pow2( cosTheta1 ) );
		float cosTheta2Sq = 1.0 - sinTheta2Sq;
		if ( cosTheta2Sq < 0.0 ) {
			return vec3( 1.0 );
		}
		float cosTheta2 = sqrt( cosTheta2Sq );
		float R0 = IorToFresnel0( iridescenceIOR, outsideIOR );
		float R12 = F_Schlick( R0, 1.0, cosTheta1 );
		float T121 = 1.0 - R12;
		float phi12 = 0.0;
		if ( iridescenceIOR < outsideIOR ) phi12 = PI;
		float phi21 = PI - phi12;
		vec3 baseIOR = Fresnel0ToIor( clamp( baseF0, 0.0, 0.9999 ) );		vec3 R1 = IorToFresnel0( baseIOR, iridescenceIOR );
		vec3 R23 = F_Schlick( R1, 1.0, cosTheta2 );
		vec3 phi23 = vec3( 0.0 );
		if ( baseIOR[ 0 ] < iridescenceIOR ) phi23[ 0 ] = PI;
		if ( baseIOR[ 1 ] < iridescenceIOR ) phi23[ 1 ] = PI;
		if ( baseIOR[ 2 ] < iridescenceIOR ) phi23[ 2 ] = PI;
		float OPD = 2.0 * iridescenceIOR * thinFilmThickness * cosTheta2;
		vec3 phi = vec3( phi21 ) + phi23;
		vec3 R123 = clamp( R12 * R23, 1e-5, 0.9999 );
		vec3 r123 = sqrt( R123 );
		vec3 Rs = pow2( T121 ) * R23 / ( vec3( 1.0 ) - R123 );
		vec3 C0 = R12 + Rs;
		I = C0;
		vec3 Cm = Rs - T121;
		for ( int m = 1; m <= 2; ++ m ) {
			Cm *= r123;
			vec3 Sm = 2.0 * evalSensitivity( float( m ) * OPD, float( m ) * phi );
			I += Cm * Sm;
		}
		return max( I, vec3( 0.0 ) );
	}
#endif`,bumpmap_pars_fragment:`#ifdef USE_BUMPMAP
	uniform sampler2D bumpMap;
	uniform float bumpScale;
	vec2 dHdxy_fwd() {
		vec2 dSTdx = dFdx( vBumpMapUv );
		vec2 dSTdy = dFdy( vBumpMapUv );
		float Hll = bumpScale * texture2D( bumpMap, vBumpMapUv ).x;
		float dBx = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdx ).x - Hll;
		float dBy = bumpScale * texture2D( bumpMap, vBumpMapUv + dSTdy ).x - Hll;
		return vec2( dBx, dBy );
	}
	vec3 perturbNormalArb( vec3 surf_pos, vec3 surf_norm, vec2 dHdxy, float faceDirection ) {
		vec3 vSigmaX = normalize( dFdx( surf_pos.xyz ) );
		vec3 vSigmaY = normalize( dFdy( surf_pos.xyz ) );
		vec3 vN = surf_norm;
		vec3 R1 = cross( vSigmaY, vN );
		vec3 R2 = cross( vN, vSigmaX );
		float fDet = dot( vSigmaX, R1 ) * faceDirection;
		vec3 vGrad = sign( fDet ) * ( dHdxy.x * R1 + dHdxy.y * R2 );
		return normalize( abs( fDet ) * surf_norm - vGrad );
	}
#endif`,clipping_planes_fragment:`#if NUM_CLIPPING_PLANES > 0
	vec4 plane;
	#ifdef ALPHA_TO_COVERAGE
		float distanceToPlane, distanceGradient;
		float clipOpacity = 1.0;
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
			distanceGradient = fwidth( distanceToPlane ) / 2.0;
			clipOpacity *= smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			if ( clipOpacity == 0.0 ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			float unionClipOpacity = 1.0;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				distanceToPlane = - dot( vClipPosition, plane.xyz ) + plane.w;
				distanceGradient = fwidth( distanceToPlane ) / 2.0;
				unionClipOpacity *= 1.0 - smoothstep( - distanceGradient, distanceGradient, distanceToPlane );
			}
			#pragma unroll_loop_end
			clipOpacity *= 1.0 - unionClipOpacity;
		#endif
		diffuseColor.a *= clipOpacity;
		if ( diffuseColor.a == 0.0 ) discard;
	#else
		#pragma unroll_loop_start
		for ( int i = 0; i < UNION_CLIPPING_PLANES; i ++ ) {
			plane = clippingPlanes[ i ];
			if ( dot( vClipPosition, plane.xyz ) > plane.w ) discard;
		}
		#pragma unroll_loop_end
		#if UNION_CLIPPING_PLANES < NUM_CLIPPING_PLANES
			bool clipped = true;
			#pragma unroll_loop_start
			for ( int i = UNION_CLIPPING_PLANES; i < NUM_CLIPPING_PLANES; i ++ ) {
				plane = clippingPlanes[ i ];
				clipped = ( dot( vClipPosition, plane.xyz ) > plane.w ) && clipped;
			}
			#pragma unroll_loop_end
			if ( clipped ) discard;
		#endif
	#endif
#endif`,clipping_planes_pars_fragment:`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
	uniform vec4 clippingPlanes[ NUM_CLIPPING_PLANES ];
#endif`,clipping_planes_pars_vertex:`#if NUM_CLIPPING_PLANES > 0
	varying vec3 vClipPosition;
#endif`,clipping_planes_vertex:`#if NUM_CLIPPING_PLANES > 0
	vClipPosition = - mvPosition.xyz;
#endif`,color_fragment:`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	diffuseColor *= vColor;
#endif`,color_pars_fragment:`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA )
	varying vec4 vColor;
#endif`,color_pars_vertex:`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	varying vec4 vColor;
#endif`,color_vertex:`#if defined( USE_COLOR ) || defined( USE_COLOR_ALPHA ) || defined( USE_INSTANCING_COLOR ) || defined( USE_BATCHING_COLOR )
	vColor = vec4( 1.0 );
#endif
#ifdef USE_COLOR_ALPHA
	vColor *= color;
#elif defined( USE_COLOR )
	vColor.rgb *= color;
#endif
#ifdef USE_INSTANCING_COLOR
	vColor.rgb *= instanceColor.rgb;
#endif
#ifdef USE_BATCHING_COLOR
	vColor *= getBatchingColor( getIndirectIndex( gl_DrawID ) );
#endif`,common:`#define PI 3.141592653589793
#define PI2 6.283185307179586
#define PI_HALF 1.5707963267948966
#define RECIPROCAL_PI 0.3183098861837907
#define RECIPROCAL_PI2 0.15915494309189535
#define EPSILON 1e-6
#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
#define whiteComplement( a ) ( 1.0 - saturate( a ) )
float pow2( const in float x ) { return x*x; }
vec3 pow2( const in vec3 x ) { return x*x; }
float pow3( const in float x ) { return x*x*x; }
float pow4( const in float x ) { float x2 = x*x; return x2*x2; }
float max3( const in vec3 v ) { return max( max( v.x, v.y ), v.z ); }
float average( const in vec3 v ) { return dot( v, vec3( 0.3333333 ) ); }
highp float rand( const in vec2 uv ) {
	const highp float a = 12.9898, b = 78.233, c = 43758.5453;
	highp float dt = dot( uv.xy, vec2( a,b ) ), sn = mod( dt, PI );
	return fract( sin( sn ) * c );
}
#ifdef HIGH_PRECISION
	float precisionSafeLength( vec3 v ) { return length( v ); }
#else
	float precisionSafeLength( vec3 v ) {
		float maxComponent = max3( abs( v ) );
		return length( v / maxComponent ) * maxComponent;
	}
#endif
struct IncidentLight {
	vec3 color;
	vec3 direction;
	bool visible;
};
struct ReflectedLight {
	vec3 directDiffuse;
	vec3 directSpecular;
	vec3 indirectDiffuse;
	vec3 indirectSpecular;
};
#ifdef USE_ALPHAHASH
	varying vec3 vPosition;
#endif
vec3 transformDirection( in vec3 dir, in mat4 matrix ) {
	return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );
}
#define inverseTransformDirection transformDirectionByInverseViewMatrix
vec3 transformNormalByInverseViewMatrix( in vec3 normal, in mat4 viewMatrix ) {
	return normalize( ( vec4( normal, 0.0 ) * viewMatrix ).xyz );
}
vec3 transformDirectionByInverseViewMatrix( in vec3 dir, in mat4 viewMatrix ) {
	return normalize( ( vec4( dir, 0.0 ) * viewMatrix ).xyz );
}
bool isPerspectiveMatrix( mat4 m ) {
	return m[ 2 ][ 3 ] == - 1.0;
}
vec2 equirectUv( in vec3 dir ) {
	float u = atan( dir.z, dir.x ) * RECIPROCAL_PI2 + 0.5;
	float v = asin( clamp( dir.y, - 1.0, 1.0 ) ) * RECIPROCAL_PI + 0.5;
	return vec2( u, v );
}
vec3 BRDF_Lambert( const in vec3 diffuseColor ) {
	return RECIPROCAL_PI * diffuseColor;
}
vec3 F_Schlick( const in vec3 f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
}
float F_Schlick( const in float f0, const in float f90, const in float dotVH ) {
	float fresnel = exp2( ( - 5.55473 * dotVH - 6.98316 ) * dotVH );
	return f0 * ( 1.0 - fresnel ) + ( f90 * fresnel );
} // validated`,cube_uv_reflection_fragment:`#ifdef ENVMAP_TYPE_CUBE_UV
	#define cubeUV_minMipLevel 4.0
	#define cubeUV_minTileSize 16.0
	float getFace( vec3 direction ) {
		vec3 absDirection = abs( direction );
		float face = - 1.0;
		if ( absDirection.x > absDirection.z ) {
			if ( absDirection.x > absDirection.y )
				face = direction.x > 0.0 ? 0.0 : 3.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		} else {
			if ( absDirection.z > absDirection.y )
				face = direction.z > 0.0 ? 2.0 : 5.0;
			else
				face = direction.y > 0.0 ? 1.0 : 4.0;
		}
		return face;
	}
	vec2 getUV( vec3 direction, float face ) {
		vec2 uv;
		if ( face == 0.0 ) {
			uv = vec2( direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 1.0 ) {
			uv = vec2( - direction.x, - direction.z ) / abs( direction.y );
		} else if ( face == 2.0 ) {
			uv = vec2( - direction.x, direction.y ) / abs( direction.z );
		} else if ( face == 3.0 ) {
			uv = vec2( - direction.z, direction.y ) / abs( direction.x );
		} else if ( face == 4.0 ) {
			uv = vec2( - direction.x, direction.z ) / abs( direction.y );
		} else {
			uv = vec2( direction.x, direction.y ) / abs( direction.z );
		}
		return 0.5 * ( uv + 1.0 );
	}
	vec3 bilinearCubeUV( sampler2D envMap, vec3 direction, float mipInt ) {
		float face = getFace( direction );
		float filterInt = max( cubeUV_minMipLevel - mipInt, 0.0 );
		mipInt = max( mipInt, cubeUV_minMipLevel );
		float faceSize = exp2( mipInt );
		highp vec2 uv = getUV( direction, face ) * ( faceSize - 2.0 ) + 1.0;
		if ( face > 2.0 ) {
			uv.y += faceSize;
			face -= 3.0;
		}
		uv.x += face * faceSize;
		uv.x += filterInt * 3.0 * cubeUV_minTileSize;
		uv.y += 4.0 * ( exp2( CUBEUV_MAX_MIP ) - faceSize );
		uv.x *= CUBEUV_TEXEL_WIDTH;
		uv.y *= CUBEUV_TEXEL_HEIGHT;
		#ifdef texture2DGradEXT
			return texture2DGradEXT( envMap, uv, vec2( 0.0 ), vec2( 0.0 ) ).rgb;
		#else
			return texture2D( envMap, uv ).rgb;
		#endif
	}
	#define cubeUV_r0 1.0
	#define cubeUV_m0 - 2.0
	#define cubeUV_r1 0.8
	#define cubeUV_m1 - 1.0
	#define cubeUV_r4 0.4
	#define cubeUV_m4 2.0
	#define cubeUV_r5 0.305
	#define cubeUV_m5 3.0
	#define cubeUV_r6 0.21
	#define cubeUV_m6 4.0
	float roughnessToMip( float roughness ) {
		float mip = 0.0;
		if ( roughness >= cubeUV_r1 ) {
			mip = ( cubeUV_r0 - roughness ) * ( cubeUV_m1 - cubeUV_m0 ) / ( cubeUV_r0 - cubeUV_r1 ) + cubeUV_m0;
		} else if ( roughness >= cubeUV_r4 ) {
			mip = ( cubeUV_r1 - roughness ) * ( cubeUV_m4 - cubeUV_m1 ) / ( cubeUV_r1 - cubeUV_r4 ) + cubeUV_m1;
		} else if ( roughness >= cubeUV_r5 ) {
			mip = ( cubeUV_r4 - roughness ) * ( cubeUV_m5 - cubeUV_m4 ) / ( cubeUV_r4 - cubeUV_r5 ) + cubeUV_m4;
		} else if ( roughness >= cubeUV_r6 ) {
			mip = ( cubeUV_r5 - roughness ) * ( cubeUV_m6 - cubeUV_m5 ) / ( cubeUV_r5 - cubeUV_r6 ) + cubeUV_m5;
		} else {
			mip = - 2.0 * log2( 1.16 * roughness );		}
		return mip;
	}
	vec4 textureCubeUV( sampler2D envMap, vec3 sampleDir, float roughness ) {
		float mip = clamp( roughnessToMip( roughness ), cubeUV_m0, CUBEUV_MAX_MIP );
		float mipF = fract( mip );
		float mipInt = floor( mip );
		vec3 color0 = bilinearCubeUV( envMap, sampleDir, mipInt );
		if ( mipF == 0.0 ) {
			return vec4( color0, 1.0 );
		} else {
			vec3 color1 = bilinearCubeUV( envMap, sampleDir, mipInt + 1.0 );
			return vec4( mix( color0, color1, mipF ), 1.0 );
		}
	}
#endif`,defaultnormal_vertex:`vec3 transformedNormal = objectNormal;
#ifdef USE_TANGENT
	vec3 transformedTangent = objectTangent;
#endif
#ifdef USE_BATCHING
	mat3 bm = mat3( batchingMatrix );
	transformedNormal /= vec3( dot( bm[ 0 ], bm[ 0 ] ), dot( bm[ 1 ], bm[ 1 ] ), dot( bm[ 2 ], bm[ 2 ] ) );
	transformedNormal = bm * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = bm * transformedTangent;
	#endif
#endif
#ifdef USE_INSTANCING
	mat3 im = mat3( instanceMatrix );
	transformedNormal /= vec3( dot( im[ 0 ], im[ 0 ] ), dot( im[ 1 ], im[ 1 ] ), dot( im[ 2 ], im[ 2 ] ) );
	transformedNormal = im * transformedNormal;
	#ifdef USE_TANGENT
		transformedTangent = im * transformedTangent;
	#endif
#endif
transformedNormal = normalMatrix * transformedNormal;
#ifdef FLIP_SIDED
	transformedNormal = - transformedNormal;
#endif
#ifdef USE_TANGENT
	transformedTangent = ( modelViewMatrix * vec4( transformedTangent, 0.0 ) ).xyz;
#endif`,displacementmap_pars_vertex:`#ifdef USE_DISPLACEMENTMAP
	uniform sampler2D displacementMap;
	uniform float displacementScale;
	uniform float displacementBias;
#endif`,displacementmap_vertex:`#ifdef USE_DISPLACEMENTMAP
	transformed += normalize( objectNormal ) * ( texture2D( displacementMap, vDisplacementMapUv ).x * displacementScale + displacementBias );
#endif`,emissivemap_fragment:`#ifdef USE_EMISSIVEMAP
	vec4 emissiveColor = texture2D( emissiveMap, vEmissiveMapUv );
	#ifdef DECODE_VIDEO_TEXTURE_EMISSIVE
		emissiveColor = sRGBTransferEOTF( emissiveColor );
	#endif
	totalEmissiveRadiance *= emissiveColor.rgb;
#endif`,emissivemap_pars_fragment:`#ifdef USE_EMISSIVEMAP
	uniform sampler2D emissiveMap;
#endif`,colorspace_fragment:`gl_FragColor = linearToOutputTexel( gl_FragColor );`,colorspace_pars_fragment:`vec4 LinearTransferOETF( in vec4 value ) {
	return value;
}
vec4 sRGBTransferEOTF( in vec4 value ) {
	return vec4( mix( pow( value.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), value.rgb * 0.0773993808, vec3( lessThanEqual( value.rgb, vec3( 0.04045 ) ) ) ), value.a );
}
vec4 sRGBTransferOETF( in vec4 value ) {
	return vec4( mix( pow( value.rgb, vec3( 0.41666 ) ) * 1.055 - vec3( 0.055 ), value.rgb * 12.92, vec3( lessThanEqual( value.rgb, vec3( 0.0031308 ) ) ) ), value.a );
}`,envmap_fragment:`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vec3 cameraToFrag;
		if ( isOrthographic ) {
			cameraToFrag = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToFrag = normalize( vWorldPosition - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vec3 reflectVec = reflect( cameraToFrag, worldNormal );
		#else
			vec3 reflectVec = refract( cameraToFrag, worldNormal, refractionRatio );
		#endif
	#else
		vec3 reflectVec = vReflect;
	#endif
	#ifdef ENVMAP_TYPE_CUBE
		vec4 envColor = textureCube( envMap, envMapRotation * reflectVec );
		#ifdef ENVMAP_BLENDING_MULTIPLY
			outgoingLight = mix( outgoingLight, outgoingLight * envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_MIX )
			outgoingLight = mix( outgoingLight, envColor.xyz, specularStrength * reflectivity );
		#elif defined( ENVMAP_BLENDING_ADD )
			outgoingLight += envColor.xyz * specularStrength * reflectivity;
		#endif
	#endif
#endif`,envmap_common_pars_fragment:`#ifdef USE_ENVMAP
	uniform float envMapIntensity;
	uniform mat3 envMapRotation;
	#ifdef ENVMAP_TYPE_CUBE
		uniform samplerCube envMap;
	#else
		uniform sampler2D envMap;
	#endif
#endif`,envmap_pars_fragment:`#ifdef USE_ENVMAP
	uniform float reflectivity;
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		varying vec3 vWorldPosition;
		uniform float refractionRatio;
	#else
		varying vec3 vReflect;
	#endif
#endif`,envmap_pars_vertex:`#ifdef USE_ENVMAP
	#if defined( USE_BUMPMAP ) || defined( USE_NORMALMAP ) || defined( PHONG ) || defined( LAMBERT )
		#define ENV_WORLDPOS
	#endif
	#ifdef ENV_WORLDPOS
		
		varying vec3 vWorldPosition;
	#else
		varying vec3 vReflect;
		uniform float refractionRatio;
	#endif
#endif`,envmap_physical_pars_fragment:`#ifdef USE_ENVMAP
	vec3 getIBLIrradiance( const in vec3 normal ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * worldNormal, 1.0 );
			return PI * envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	vec3 getIBLRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
		#ifdef ENVMAP_TYPE_CUBE_UV
			vec3 reflectVec = reflect( - viewDir, normal );
			reflectVec = normalize( mix( reflectVec, normal, pow4( roughness ) ) );
			reflectVec = transformDirectionByInverseViewMatrix( reflectVec, viewMatrix );
			vec4 envMapColor = textureCubeUV( envMap, envMapRotation * reflectVec, roughness );
			return envMapColor.rgb * envMapIntensity;
		#else
			return vec3( 0.0 );
		#endif
	}
	#ifdef USE_RETROREFLECTION
		vec3 getIBLRetroRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 retroVec = normalize( mix( viewDir, normal, pow4( roughness ) ) );
				retroVec = transformDirectionByInverseViewMatrix( retroVec, viewMatrix );
				vec4 envMapColor = textureCubeUV( envMap, envMapRotation * retroVec, roughness );
				return envMapColor.rgb * envMapIntensity;
			#else
				return vec3( 0.0 );
			#endif
		}
	#endif
	#ifdef USE_ANISOTROPY
		vec3 getIBLAnisotropyRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
			#ifdef ENVMAP_TYPE_CUBE_UV
				vec3 bentNormal = cross( bitangent, viewDir );
				bentNormal = normalize( cross( bentNormal, bitangent ) );
				bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
				return getIBLRadiance( viewDir, bentNormal, roughness );
			#else
				return vec3( 0.0 );
			#endif
		}
		#ifdef USE_RETROREFLECTION
			vec3 getIBLAnisotropyRetroRadiance( const in vec3 viewDir, const in vec3 normal, const in float roughness, const in vec3 bitangent, const in float anisotropy ) {
				#ifdef ENVMAP_TYPE_CUBE_UV
					vec3 bentNormal = cross( bitangent, viewDir );
					bentNormal = normalize( cross( bentNormal, bitangent ) );
					bentNormal = normalize( mix( bentNormal, normal, pow2( pow2( 1.0 - anisotropy * ( 1.0 - roughness ) ) ) ) );
					return getIBLRetroRadiance( viewDir, bentNormal, roughness );
				#else
					return vec3( 0.0 );
				#endif
			}
		#endif
	#endif
#endif`,envmap_vertex:`#ifdef USE_ENVMAP
	#ifdef ENV_WORLDPOS
		vWorldPosition = worldPosition.xyz;
	#else
		vec3 cameraToVertex;
		if ( isOrthographic ) {
			cameraToVertex = normalize( vec3( - viewMatrix[ 0 ][ 2 ], - viewMatrix[ 1 ][ 2 ], - viewMatrix[ 2 ][ 2 ] ) );
		} else {
			cameraToVertex = normalize( worldPosition.xyz - cameraPosition );
		}
		vec3 worldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
		#ifdef ENVMAP_MODE_REFLECTION
			vReflect = reflect( cameraToVertex, worldNormal );
		#else
			vReflect = refract( cameraToVertex, worldNormal, refractionRatio );
		#endif
	#endif
#endif`,fog_vertex:`#ifdef USE_FOG
	vFogDepth = - mvPosition.z;
#endif`,fog_pars_vertex:`#ifdef USE_FOG
	varying float vFogDepth;
#endif`,fog_fragment:`#ifdef USE_FOG
	#ifdef FOG_EXP2
		float fogFactor = 1.0 - exp( - fogDensity * fogDensity * vFogDepth * vFogDepth );
	#else
		float fogFactor = smoothstep( fogNear, fogFar, vFogDepth );
	#endif
	gl_FragColor.rgb = mix( gl_FragColor.rgb, fogColor, fogFactor );
#endif`,fog_pars_fragment:`#ifdef USE_FOG
	uniform vec3 fogColor;
	varying float vFogDepth;
	#ifdef FOG_EXP2
		uniform float fogDensity;
	#else
		uniform float fogNear;
		uniform float fogFar;
	#endif
#endif`,gradientmap_pars_fragment:`#ifdef USE_GRADIENTMAP
	uniform sampler2D gradientMap;
#endif
vec3 getGradientIrradiance( vec3 normal, vec3 lightDirection ) {
	float dotNL = dot( normal, lightDirection );
	vec2 coord = vec2( dotNL * 0.5 + 0.5, 0.0 );
	#ifdef USE_GRADIENTMAP
		return vec3( texture2D( gradientMap, coord ).r );
	#else
		vec2 fw = fwidth( coord ) * 0.5;
		return mix( vec3( 0.7 ), vec3( 1.0 ), smoothstep( 0.7 - fw.x, 0.7 + fw.x, coord.x ) );
	#endif
}`,lightmap_pars_fragment:`#ifdef USE_LIGHTMAP
	uniform sampler2D lightMap;
	uniform float lightMapIntensity;
#endif`,lights_lambert_fragment:`LambertMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularStrength = specularStrength;`,lights_lambert_pars_fragment:`varying vec3 vViewPosition;
struct LambertMaterial {
	vec3 diffuseColor;
	float specularStrength;
};
void RE_Direct_Lambert( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Lambert( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in LambertMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Lambert
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Lambert`,lights_pars_begin:`uniform bool receiveShadow;
uniform vec3 ambientLightColor;
#if defined( USE_LIGHT_PROBES )
	uniform vec3 lightProbe[ 9 ];
#endif
vec3 shGetIrradianceAt( in vec3 normal, in vec3 shCoefficients[ 9 ] ) {
	float x = normal.x, y = normal.y, z = normal.z;
	vec3 result = shCoefficients[ 0 ] * 0.886227;
	result += shCoefficients[ 1 ] * 2.0 * 0.511664 * y;
	result += shCoefficients[ 2 ] * 2.0 * 0.511664 * z;
	result += shCoefficients[ 3 ] * 2.0 * 0.511664 * x;
	result += shCoefficients[ 4 ] * 2.0 * 0.429043 * x * y;
	result += shCoefficients[ 5 ] * 2.0 * 0.429043 * y * z;
	result += shCoefficients[ 6 ] * ( 0.743125 * z * z - 0.247708 );
	result += shCoefficients[ 7 ] * 2.0 * 0.429043 * x * z;
	result += shCoefficients[ 8 ] * 0.429043 * ( x * x - y * y );
	return result;
}
vec3 getLightProbeIrradiance( const in vec3 lightProbe[ 9 ], const in vec3 normal ) {
	vec3 worldNormal = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec3 irradiance = shGetIrradianceAt( worldNormal, lightProbe );
	return irradiance;
}
vec3 getAmbientLightIrradiance( const in vec3 ambientLightColor ) {
	vec3 irradiance = ambientLightColor;
	return irradiance;
}
float getDistanceAttenuation( const in float lightDistance, const in float cutoffDistance, const in float decayExponent ) {
	float distanceFalloff = 1.0 / max( pow( lightDistance, decayExponent ), 0.01 );
	if ( cutoffDistance > 0.0 ) {
		distanceFalloff *= pow2( saturate( 1.0 - pow4( lightDistance / cutoffDistance ) ) );
	}
	return distanceFalloff;
}
float getSpotAttenuation( const in float coneCosine, const in float penumbraCosine, const in float angleCosine ) {
	return smoothstep( coneCosine, penumbraCosine, angleCosine );
}
#if NUM_SUN_LIGHTS > 0
	struct SunLight {
		vec3 direction;
		vec3 color;
	};
	uniform SunLight sunLights[ NUM_SUN_LIGHTS ];
	void getSunLightInfo( const in SunLight sunLight, out IncidentLight light ) {
		light.color = sunLight.color;
		light.direction = sunLight.direction;
		light.visible = true;
	}
#endif
#if NUM_DIR_LIGHTS > 0
	struct DirectionalLight {
		vec3 direction;
		vec3 color;
	};
	uniform DirectionalLight directionalLights[ NUM_DIR_LIGHTS ];
	void getDirectionalLightInfo( const in DirectionalLight directionalLight, out IncidentLight light ) {
		light.color = directionalLight.color;
		light.direction = directionalLight.direction;
		light.visible = true;
	}
#endif
#if NUM_POINT_LIGHTS > 0
	struct PointLight {
		vec3 position;
		vec3 color;
		float distance;
		float decay;
	};
	uniform PointLight pointLights[ NUM_POINT_LIGHTS ];
	void getPointLightInfo( const in PointLight pointLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = pointLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float lightDistance = length( lVector );
		light.color = pointLight.color;
		light.color *= getDistanceAttenuation( lightDistance, pointLight.distance, pointLight.decay );
		light.visible = ( light.color != vec3( 0.0 ) );
	}
#endif
#if NUM_SPOT_LIGHTS > 0
	struct SpotLight {
		vec3 position;
		vec3 direction;
		vec3 color;
		float distance;
		float decay;
		float coneCos;
		float penumbraCos;
	};
	uniform SpotLight spotLights[ NUM_SPOT_LIGHTS ];
	void getSpotLightInfo( const in SpotLight spotLight, const in vec3 geometryPosition, out IncidentLight light ) {
		vec3 lVector = spotLight.position - geometryPosition;
		light.direction = normalize( lVector );
		float angleCos = dot( light.direction, spotLight.direction );
		float spotAttenuation = getSpotAttenuation( spotLight.coneCos, spotLight.penumbraCos, angleCos );
		if ( spotAttenuation > 0.0 ) {
			float lightDistance = length( lVector );
			light.color = spotLight.color * spotAttenuation;
			light.color *= getDistanceAttenuation( lightDistance, spotLight.distance, spotLight.decay );
			light.visible = ( light.color != vec3( 0.0 ) );
		} else {
			light.color = vec3( 0.0 );
			light.visible = false;
		}
	}
#endif
#if NUM_RECT_AREA_LIGHTS > 0
	struct RectAreaLight {
		vec3 color;
		vec3 position;
		vec3 halfWidth;
		vec3 halfHeight;
	};
	uniform sampler2D ltc_1;	uniform sampler2D ltc_2;
	uniform RectAreaLight rectAreaLights[ NUM_RECT_AREA_LIGHTS ];
#endif
#if NUM_HEMI_LIGHTS > 0
	struct HemisphereLight {
		vec3 direction;
		vec3 skyColor;
		vec3 groundColor;
	};
	uniform HemisphereLight hemisphereLights[ NUM_HEMI_LIGHTS ];
	vec3 getHemisphereLightIrradiance( const in HemisphereLight hemiLight, const in vec3 normal ) {
		float dotNL = dot( normal, hemiLight.direction );
		float hemiDiffuseWeight = 0.5 * dotNL + 0.5;
		vec3 irradiance = mix( hemiLight.groundColor, hemiLight.skyColor, hemiDiffuseWeight );
		return irradiance;
	}
#endif
#include <lightprobes_pars_fragment>`,lights_toon_fragment:`ToonMaterial material;
material.diffuseColor = diffuseColor.rgb;`,lights_toon_pars_fragment:`varying vec3 vViewPosition;
struct ToonMaterial {
	vec3 diffuseColor;
};
void RE_Direct_Toon( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 irradiance = getGradientIrradiance( geometryNormal, directLight.direction ) * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
void RE_IndirectDiffuse_Toon( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in ToonMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_Toon
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Toon`,lights_phong_fragment:`BlinnPhongMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.specularColor = specular;
material.specularShininess = shininess;
material.specularStrength = specularStrength;`,lights_phong_pars_fragment:`varying vec3 vViewPosition;
struct BlinnPhongMaterial {
	vec3 diffuseColor;
	vec3 specularColor;
	float specularShininess;
	float specularStrength;
};
void RE_Direct_BlinnPhong( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
	reflectedLight.directSpecular += irradiance * BRDF_BlinnPhong( directLight.direction, geometryViewDir, geometryNormal, material.specularColor, material.specularShininess ) * material.specularStrength;
}
void RE_IndirectDiffuse_BlinnPhong( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in BlinnPhongMaterial material, inout ReflectedLight reflectedLight ) {
	reflectedLight.indirectDiffuse += irradiance * BRDF_Lambert( material.diffuseColor );
}
#define RE_Direct				RE_Direct_BlinnPhong
#define RE_IndirectDiffuse		RE_IndirectDiffuse_BlinnPhong`,lights_physical_fragment:`PhysicalMaterial material;
material.diffuseColor = diffuseColor.rgb;
material.diffuseContribution = diffuseColor.rgb * ( 1.0 - metalnessFactor );
material.metalness = metalnessFactor;
vec3 dxy = max( abs( dFdx( nonPerturbedNormal ) ), abs( dFdy( nonPerturbedNormal ) ) );
float geometryRoughness = max( max( dxy.x, dxy.y ), dxy.z );
material.roughness = max( roughnessFactor, 0.0525 );material.roughness += geometryRoughness;
material.roughness = min( material.roughness, 1.0 );
#ifdef IOR
	material.ior = ior;
	#ifdef USE_SPECULAR
		float specularIntensityFactor = specularIntensity;
		vec3 specularColorFactor = specularColor;
		#ifdef USE_SPECULAR_COLORMAP
			specularColorFactor *= texture2D( specularColorMap, vSpecularColorMapUv ).rgb;
		#endif
		#ifdef USE_SPECULAR_INTENSITYMAP
			specularIntensityFactor *= texture2D( specularIntensityMap, vSpecularIntensityMapUv ).a;
		#endif
		material.specularF90 = mix( specularIntensityFactor, 1.0, metalnessFactor );
	#else
		float specularIntensityFactor = 1.0;
		vec3 specularColorFactor = vec3( 1.0 );
		material.specularF90 = 1.0;
	#endif
	material.specularColor = min( pow2( ( material.ior - 1.0 ) / ( material.ior + 1.0 ) ) * specularColorFactor, vec3( 1.0 ) ) * specularIntensityFactor;
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
#else
	material.specularColor = vec3( 0.04 );
	material.specularColorBlended = mix( material.specularColor, diffuseColor.rgb, metalnessFactor );
	material.specularF90 = 1.0;
#endif
#ifdef USE_CLEARCOAT
	material.clearcoat = clearcoat;
	material.clearcoatRoughness = clearcoatRoughness;
	material.clearcoatF0 = vec3( 0.04 );
	material.clearcoatF90 = 1.0;
	#ifdef USE_CLEARCOATMAP
		material.clearcoat *= texture2D( clearcoatMap, vClearcoatMapUv ).x;
	#endif
	#ifdef USE_CLEARCOAT_ROUGHNESSMAP
		material.clearcoatRoughness *= texture2D( clearcoatRoughnessMap, vClearcoatRoughnessMapUv ).y;
	#endif
	material.clearcoat = saturate( material.clearcoat );	material.clearcoatRoughness = max( material.clearcoatRoughness, 0.0525 );
	material.clearcoatRoughness += geometryRoughness;
	material.clearcoatRoughness = min( material.clearcoatRoughness, 1.0 );
#endif
#ifdef USE_DISPERSION
	material.dispersion = dispersion;
#endif
#ifdef USE_RETROREFLECTION
	material.retroreflectivity = retroreflectivity;
#endif
#ifdef USE_IRIDESCENCE
	material.iridescence = iridescence;
	material.iridescenceIOR = iridescenceIOR;
	#ifdef USE_IRIDESCENCEMAP
		material.iridescence *= texture2D( iridescenceMap, vIridescenceMapUv ).r;
	#endif
	#ifdef USE_IRIDESCENCE_THICKNESSMAP
		material.iridescenceThickness = (iridescenceThicknessMaximum - iridescenceThicknessMinimum) * texture2D( iridescenceThicknessMap, vIridescenceThicknessMapUv ).g + iridescenceThicknessMinimum;
	#else
		material.iridescenceThickness = iridescenceThicknessMaximum;
	#endif
#endif
#ifdef USE_SHEEN
	material.sheenColor = sheenColor;
	#ifdef USE_SHEEN_COLORMAP
		material.sheenColor *= texture2D( sheenColorMap, vSheenColorMapUv ).rgb;
	#endif
	material.sheenRoughness = clamp( sheenRoughness, 0.0001, 1.0 );
	#ifdef USE_SHEEN_ROUGHNESSMAP
		material.sheenRoughness *= texture2D( sheenRoughnessMap, vSheenRoughnessMapUv ).a;
	#endif
#endif
#ifdef USE_ANISOTROPY
	#ifdef USE_ANISOTROPYMAP
		mat2 anisotropyMat = mat2( anisotropyVector.x, anisotropyVector.y, - anisotropyVector.y, anisotropyVector.x );
		vec3 anisotropyPolar = texture2D( anisotropyMap, vAnisotropyMapUv ).rgb;
		vec2 anisotropyV = anisotropyMat * normalize( 2.0 * anisotropyPolar.rg - vec2( 1.0 ) ) * anisotropyPolar.b;
	#else
		vec2 anisotropyV = anisotropyVector;
	#endif
	material.anisotropy = length( anisotropyV );
	if( material.anisotropy == 0.0 ) {
		anisotropyV = vec2( 1.0, 0.0 );
	} else {
		anisotropyV /= material.anisotropy;
		material.anisotropy = saturate( material.anisotropy );
	}
	material.alphaT = mix( pow2( material.roughness ), 1.0, pow2( material.anisotropy ) );
	material.anisotropyT = tbn[ 0 ] * anisotropyV.x + tbn[ 1 ] * anisotropyV.y;
	material.anisotropyB = tbn[ 1 ] * anisotropyV.x - tbn[ 0 ] * anisotropyV.y;
#endif`,lights_physical_pars_fragment:`uniform sampler2D dfgLUT;
struct PhysicalMaterial {
	vec3 diffuseColor;
	vec3 diffuseContribution;
	vec3 specularColor;
	vec3 specularColorBlended;
	float roughness;
	float metalness;
	float specularF90;
	float dispersion;
	vec2 dfg;
	vec3 multiScatteringCompensation;
	#ifdef USE_RETROREFLECTION
		float retroreflectivity;
	#endif
	#ifdef USE_CLEARCOAT
		float clearcoat;
		float clearcoatRoughness;
		vec3 clearcoatF0;
		float clearcoatF90;
	#endif
	#ifdef USE_IRIDESCENCE
		float iridescence;
		float iridescenceIOR;
		float iridescenceThickness;
		vec3 iridescenceFresnel;
		vec3 iridescenceF0Dielectric;
		vec3 iridescenceF0Metallic;
	#endif
	#ifdef USE_SHEEN
		vec3 sheenColor;
		float sheenRoughness;
	#endif
	#ifdef IOR
		float ior;
	#endif
	#ifdef USE_TRANSMISSION
		float transmission;
		float transmissionAlpha;
		float thickness;
		float attenuationDistance;
		vec3 attenuationColor;
	#endif
	#ifdef USE_ANISOTROPY
		float anisotropy;
		float alphaT;
		vec3 anisotropyT;
		vec3 anisotropyB;
	#endif
};
vec3 clearcoatSpecularDirect = vec3( 0.0 );
vec3 clearcoatSpecularIndirect = vec3( 0.0 );
vec3 sheenSpecularDirect = vec3( 0.0 );
vec3 sheenSpecularIndirect = vec3(0.0 );
vec3 Schlick_to_F0( const in vec3 f, const in float f90, const in float dotVH ) {
    float x = clamp( 1.0 - dotVH, 0.0, 1.0 );
    float x2 = x * x;
    float x5 = clamp( x * x2 * x2, 0.0, 0.9999 );
    return ( f - vec3( f90 ) * x5 ) / ( 1.0 - x5 );
}
float V_GGX_SmithCorrelated( const in float alpha, const in float dotNL, const in float dotNV ) {
	float a2 = pow2( alpha );
	float gv = dotNL * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNV ) );
	float gl = dotNV * sqrt( a2 + ( 1.0 - a2 ) * pow2( dotNL ) );
	return 0.5 / max( gv + gl, EPSILON );
}
float D_GGX( const in float alpha, const in float dotNH ) {
	float a2 = pow2( alpha );
	float denom = pow2( dotNH ) * ( a2 - 1.0 ) + 1.0;
	return RECIPROCAL_PI * a2 / pow2( denom );
}
#ifdef USE_ANISOTROPY
	float V_GGX_SmithCorrelated_Anisotropic( const in float alphaT, const in float alphaB, const in float dotTV, const in float dotBV, const in float dotTL, const in float dotBL, const in float dotNV, const in float dotNL ) {
		float gv = dotNL * length( vec3( alphaT * dotTV, alphaB * dotBV, dotNV ) );
		float gl = dotNV * length( vec3( alphaT * dotTL, alphaB * dotBL, dotNL ) );
		return 0.5 / max( gv + gl, EPSILON );
	}
	float D_GGX_Anisotropic( const in float alphaT, const in float alphaB, const in float dotNH, const in float dotTH, const in float dotBH ) {
		float a2 = alphaT * alphaB;
		highp vec3 v = vec3( alphaB * dotTH, alphaT * dotBH, a2 * dotNH );
		highp float v2 = dot( v, v );
		float w2 = a2 / v2;
		return RECIPROCAL_PI * a2 * pow2 ( w2 );
	}
#endif
#ifdef USE_CLEARCOAT
	vec3 BRDF_GGX_Clearcoat( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material) {
		vec3 f0 = material.clearcoatF0;
		float f90 = material.clearcoatF90;
		float roughness = material.clearcoatRoughness;
		float alpha = pow2( roughness );
		vec3 halfDir = normalize( lightDir + viewDir );
		float dotNL = saturate( dot( normal, lightDir ) );
		float dotNV = saturate( dot( normal, viewDir ) );
		float dotNH = saturate( dot( normal, halfDir ) );
		float dotVH = saturate( dot( viewDir, halfDir ) );
		vec3 F = F_Schlick( f0, f90, dotVH );
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
		return F * ( V * D );
	}
#endif
vec3 BRDF_GGX( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, const in PhysicalMaterial material ) {
	vec3 f0 = material.specularColorBlended;
	float f90 = material.specularF90;
	float roughness = material.roughness;
	float alpha = pow2( roughness );
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float dotVH = saturate( dot( viewDir, halfDir ) );
	vec3 F = F_Schlick( f0, f90, dotVH );
	#ifdef USE_IRIDESCENCE
		F = mix( F, material.iridescenceFresnel, material.iridescence );
	#endif
	#ifdef USE_ANISOTROPY
		float dotTL = dot( material.anisotropyT, lightDir );
		float dotTV = dot( material.anisotropyT, viewDir );
		float dotTH = dot( material.anisotropyT, halfDir );
		float dotBL = dot( material.anisotropyB, lightDir );
		float dotBV = dot( material.anisotropyB, viewDir );
		float dotBH = dot( material.anisotropyB, halfDir );
		float V = V_GGX_SmithCorrelated_Anisotropic( material.alphaT, alpha, dotTV, dotBV, dotTL, dotBL, dotNV, dotNL );
		float D = D_GGX_Anisotropic( material.alphaT, alpha, dotNH, dotTH, dotBH );
	#else
		float V = V_GGX_SmithCorrelated( alpha, dotNL, dotNV );
		float D = D_GGX( alpha, dotNH );
	#endif
	return F * ( V * D );
}
vec2 LTC_Uv( const in vec3 N, const in vec3 V, const in float roughness ) {
	const float LUT_SIZE = 64.0;
	const float LUT_SCALE = ( LUT_SIZE - 1.0 ) / LUT_SIZE;
	const float LUT_BIAS = 0.5 / LUT_SIZE;
	float dotNV = saturate( dot( N, V ) );
	vec2 uv = vec2( roughness, sqrt( 1.0 - dotNV ) );
	uv = uv * LUT_SCALE + LUT_BIAS;
	return uv;
}
float LTC_ClippedSphereFormFactor( const in vec3 f ) {
	float l = length( f );
	return max( ( l * l + f.z ) / ( l + 1.0 ), 0.0 );
}
vec3 LTC_EdgeVectorFormFactor( const in vec3 v1, const in vec3 v2 ) {
	float x = dot( v1, v2 );
	float y = abs( x );
	float a = 0.8543985 + ( 0.4965155 + 0.0145206 * y ) * y;
	float b = 3.4175940 + ( 4.1616724 + y ) * y;
	float v = a / b;
	float theta_sintheta = ( x > 0.0 ) ? v : 0.5 * inversesqrt( max( 1.0 - x * x, 1e-7 ) ) - v;
	return cross( v1, v2 ) * theta_sintheta;
}
vec3 LTC_Evaluate( const in vec3 N, const in vec3 V, const in vec3 P, const in mat3 mInv, const in vec3 rectCoords[ 4 ] ) {
	vec3 v1 = rectCoords[ 1 ] - rectCoords[ 0 ];
	vec3 v2 = rectCoords[ 3 ] - rectCoords[ 0 ];
	vec3 lightNormal = cross( v1, v2 );
	if( dot( lightNormal, P - rectCoords[ 0 ] ) < 0.0 ) return vec3( 0.0 );
	vec3 T1, T2;
	T1 = normalize( V - N * dot( V, N ) );
	T2 = - cross( N, T1 );
	mat3 mat = mInv * transpose( mat3( T1, T2, N ) );
	vec3 coords[ 4 ];
	coords[ 0 ] = mat * ( rectCoords[ 0 ] - P );
	coords[ 1 ] = mat * ( rectCoords[ 1 ] - P );
	coords[ 2 ] = mat * ( rectCoords[ 2 ] - P );
	coords[ 3 ] = mat * ( rectCoords[ 3 ] - P );
	coords[ 0 ] = normalize( coords[ 0 ] );
	coords[ 1 ] = normalize( coords[ 1 ] );
	coords[ 2 ] = normalize( coords[ 2 ] );
	coords[ 3 ] = normalize( coords[ 3 ] );
	vec3 vectorFormFactor = vec3( 0.0 );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 0 ], coords[ 1 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 1 ], coords[ 2 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 2 ], coords[ 3 ] );
	vectorFormFactor += LTC_EdgeVectorFormFactor( coords[ 3 ], coords[ 0 ] );
	float result = LTC_ClippedSphereFormFactor( vectorFormFactor );
	return vec3( result );
}
#if defined( USE_SHEEN )
float D_Charlie( float roughness, float dotNH ) {
	float alpha = pow2( roughness );
	float invAlpha = 1.0 / alpha;
	float cos2h = dotNH * dotNH;
	float sin2h = max( 1.0 - cos2h, 0.0078125 );
	return ( 2.0 + invAlpha ) * pow( sin2h, invAlpha * 0.5 ) / ( 2.0 * PI );
}
float V_Neubelt( float dotNV, float dotNL ) {
	return saturate( 1.0 / ( 4.0 * ( dotNL + dotNV - dotNL * dotNV ) ) );
}
vec3 BRDF_Sheen( const in vec3 lightDir, const in vec3 viewDir, const in vec3 normal, vec3 sheenColor, const in float sheenRoughness ) {
	vec3 halfDir = normalize( lightDir + viewDir );
	float dotNL = saturate( dot( normal, lightDir ) );
	float dotNV = saturate( dot( normal, viewDir ) );
	float dotNH = saturate( dot( normal, halfDir ) );
	float D = D_Charlie( sheenRoughness, dotNH );
	float V = V_Neubelt( dotNV, dotNL );
	return sheenColor * ( D * V );
}
#endif
float IBLSheenBRDF( const in vec3 normal, const in vec3 viewDir, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	float r2 = roughness * roughness;
	float rInv = 1.0 / ( roughness + 0.1 );
	float a = -1.9362 + 1.0678 * roughness + 0.4573 * r2 - 0.8469 * rInv;
	float b = -0.6014 + 0.5538 * roughness - 0.4670 * r2 - 0.1255 * rInv;
	float DG = exp( a * dotNV + b );
	return saturate( DG );
}
vec3 EnvironmentBRDF( const in vec3 normal, const in vec3 viewDir, const in vec3 specularColor, const in float specularF90, const in float roughness ) {
	float dotNV = saturate( dot( normal, viewDir ) );
	vec2 fab = texture2D( dfgLUT, vec2( roughness, dotNV ) ).rg;
	return specularColor * fab.x + specularF90 * fab.y;
}
#ifdef USE_IRIDESCENCE
void computeMultiscatteringIridescence( const in vec2 fab, const in vec3 specularColor, const in float specularF90, const in float iridescence, const in vec3 iridescenceF0, inout vec3 singleScatter, inout vec3 multiScatter ) {
#else
void computeMultiscattering( const in vec2 fab, const in vec3 specularColor, const in float specularF90, inout vec3 singleScatter, inout vec3 multiScatter ) {
#endif
	#ifdef USE_IRIDESCENCE
		vec3 Fr = mix( specularColor, iridescenceF0, iridescence );
	#else
		vec3 Fr = specularColor;
	#endif
	vec3 FssEss = Fr * fab.x + specularF90 * fab.y;
	float Ess = fab.x + fab.y;
	float Ems = 1.0 - Ess;
	vec3 Favg = Fr + ( 1.0 - Fr ) * 0.047619;	vec3 Fms = FssEss * Favg / ( 1.0 - Ems * Favg );
	singleScatter += FssEss;
	multiScatter += Fms * Ems;
}
#if NUM_RECT_AREA_LIGHTS > 0
	void RE_Direct_RectArea_Physical( const in RectAreaLight rectAreaLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
		vec3 normal = geometryNormal;
		vec3 viewDir = geometryViewDir;
		vec3 position = geometryPosition;
		vec3 lightPos = rectAreaLight.position;
		vec3 halfWidth = rectAreaLight.halfWidth;
		vec3 halfHeight = rectAreaLight.halfHeight;
		vec3 lightColor = rectAreaLight.color;
		float roughness = material.roughness;
		vec3 rectCoords[ 4 ];
		rectCoords[ 0 ] = lightPos + halfWidth - halfHeight;		rectCoords[ 1 ] = lightPos - halfWidth - halfHeight;
		rectCoords[ 2 ] = lightPos - halfWidth + halfHeight;
		rectCoords[ 3 ] = lightPos + halfWidth + halfHeight;
		vec2 uv = LTC_Uv( normal, viewDir, roughness );
		vec4 t1 = texture2D( ltc_1, uv );
		vec4 t2 = texture2D( ltc_2, uv );
		mat3 mInv = mat3(
			vec3( t1.x, 0, t1.y ),
			vec3(    0, 1,    0 ),
			vec3( t1.z, 0, t1.w )
		);
		vec3 fresnel = ( material.specularColorBlended * t2.x + ( material.specularF90 - material.specularColorBlended ) * t2.y );
		reflectedLight.directSpecular += lightColor * fresnel * LTC_Evaluate( normal, viewDir, position, mInv, rectCoords );
		reflectedLight.directDiffuse += lightColor * material.diffuseContribution * LTC_Evaluate( normal, viewDir, position, mat3( 1.0 ), rectCoords );
		#ifdef USE_CLEARCOAT
			vec3 Ncc = geometryClearcoatNormal;
			vec2 uvClearcoat = LTC_Uv( Ncc, viewDir, material.clearcoatRoughness );
			vec4 t1Clearcoat = texture2D( ltc_1, uvClearcoat );
			vec4 t2Clearcoat = texture2D( ltc_2, uvClearcoat );
			mat3 mInvClearcoat = mat3(
				vec3( t1Clearcoat.x, 0, t1Clearcoat.y ),
				vec3(             0, 1,             0 ),
				vec3( t1Clearcoat.z, 0, t1Clearcoat.w )
			);
			vec3 fresnelClearcoat = material.clearcoatF0 * t2Clearcoat.x + ( material.clearcoatF90 - material.clearcoatF0 ) * t2Clearcoat.y;
			clearcoatSpecularDirect += lightColor * fresnelClearcoat * LTC_Evaluate( Ncc, viewDir, position, mInvClearcoat, rectCoords );
		#endif
	}
#endif
void RE_Direct_Physical( const in IncidentLight directLight, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	float dotNL = saturate( dot( geometryNormal, directLight.direction ) );
	vec3 irradiance = dotNL * directLight.color;
	#ifdef USE_CLEARCOAT
		float dotNLcc = saturate( dot( geometryClearcoatNormal, directLight.direction ) );
		vec3 ccIrradiance = dotNLcc * directLight.color;
		clearcoatSpecularDirect += ccIrradiance * BRDF_GGX_Clearcoat( directLight.direction, geometryViewDir, geometryClearcoatNormal, material );
	#endif
	#ifdef USE_SHEEN
 
 		sheenSpecularDirect += irradiance * BRDF_Sheen( directLight.direction, geometryViewDir, geometryNormal, material.sheenColor, material.sheenRoughness );
 
 		float sheenAlbedoV = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
 		float sheenAlbedoL = IBLSheenBRDF( geometryNormal, directLight.direction, material.sheenRoughness );
 
 		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * max( sheenAlbedoV, sheenAlbedoL );
 
 		irradiance *= sheenEnergyComp;
 
 	#endif
	vec3 specularBRDF = BRDF_GGX( directLight.direction, geometryViewDir, geometryNormal, material );
	#ifdef USE_RETROREFLECTION
		vec3 retroViewDir = reflect( - geometryViewDir, geometryNormal );
		vec3 retroSpecularBRDF = BRDF_GGX( directLight.direction, retroViewDir, geometryNormal, material );
		specularBRDF = mix( specularBRDF, retroSpecularBRDF, saturate( material.retroreflectivity ) );
	#endif
	reflectedLight.directSpecular += irradiance * specularBRDF * material.multiScatteringCompensation;
	vec3 halfDir = normalize( directLight.direction + geometryViewDir );
	float dotVH = saturate( dot( geometryViewDir, halfDir ) );
	vec3 F = F_Schlick( material.specularColor, material.specularF90, dotVH );
	#ifdef USE_RETROREFLECTION
		vec3 retroHalfDir = normalize( directLight.direction + retroViewDir );
		float dotRetroVH = saturate( dot( retroViewDir, retroHalfDir ) );
		vec3 retroF = F_Schlick( material.specularColor, material.specularF90, dotRetroVH );
		F = mix( F, retroF, saturate( material.retroreflectivity ) );
	#endif
	reflectedLight.directDiffuse += irradiance * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - F );
}
void RE_IndirectDiffuse_Physical( const in vec3 irradiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight ) {
	vec3 singleScattering = vec3( 0.0 );
	vec3 multiScattering = vec3( 0.0 );
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( material.dfg, material.specularColor, material.specularF90, material.iridescence, material.iridescenceF0Dielectric, singleScattering, multiScattering );
	#else
		computeMultiscattering( material.dfg, material.specularColor, material.specularF90, singleScattering, multiScattering );
	#endif
	vec3 diffuse = irradiance * BRDF_Lambert( material.diffuseContribution ) * ( 1.0 - singleScattering - multiScattering );
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		sheenSpecularIndirect += irradiance * material.sheenColor * sheenAlbedo * RECIPROCAL_PI;
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		diffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectDiffuse += diffuse;
}
void RE_IndirectSpecular_Physical( const in vec3 radiance, const in vec3 irradiance, const in vec3 clearcoatRadiance, const in vec3 geometryPosition, const in vec3 geometryNormal, const in vec3 geometryViewDir, const in vec3 geometryClearcoatNormal, const in PhysicalMaterial material, inout ReflectedLight reflectedLight) {
	#ifdef USE_CLEARCOAT
		clearcoatSpecularIndirect += clearcoatRadiance * EnvironmentBRDF( geometryClearcoatNormal, geometryViewDir, material.clearcoatF0, material.clearcoatF90, material.clearcoatRoughness );
	#endif
	#ifdef USE_SHEEN
		sheenSpecularIndirect += irradiance * material.sheenColor * IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness ) * RECIPROCAL_PI;
 	#endif
	vec3 singleScatteringDielectric = vec3( 0.0 );
	vec3 multiScatteringDielectric = vec3( 0.0 );
	vec3 singleScatteringMetallic = vec3( 0.0 );
	vec3 multiScatteringMetallic = vec3( 0.0 );
	#ifdef USE_IRIDESCENCE
		computeMultiscatteringIridescence( material.dfg, material.specularColor, material.specularF90, material.iridescence, material.iridescenceF0Dielectric, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscatteringIridescence( material.dfg, material.diffuseColor, material.specularF90, material.iridescence, material.iridescenceF0Metallic, singleScatteringMetallic, multiScatteringMetallic );
	#else
		computeMultiscattering( material.dfg, material.specularColor, material.specularF90, singleScatteringDielectric, multiScatteringDielectric );
		computeMultiscattering( material.dfg, material.diffuseColor, material.specularF90, singleScatteringMetallic, multiScatteringMetallic );
	#endif
	vec3 singleScattering = mix( singleScatteringDielectric, singleScatteringMetallic, material.metalness );
	vec3 multiScattering = mix( multiScatteringDielectric, multiScatteringMetallic, material.metalness );
	vec3 totalScatteringDielectric = singleScatteringDielectric + multiScatteringDielectric;
	vec3 diffuse = material.diffuseContribution * ( 1.0 - totalScatteringDielectric );
	vec3 cosineWeightedIrradiance = irradiance * RECIPROCAL_PI;
	vec3 indirectSpecular = radiance * singleScattering;
	indirectSpecular += multiScattering * cosineWeightedIrradiance;
	vec3 indirectDiffuse = diffuse * cosineWeightedIrradiance;
	#ifdef USE_SHEEN
		float sheenAlbedo = IBLSheenBRDF( geometryNormal, geometryViewDir, material.sheenRoughness );
		float sheenEnergyComp = 1.0 - max3( material.sheenColor ) * sheenAlbedo;
		indirectSpecular *= sheenEnergyComp;
		indirectDiffuse *= sheenEnergyComp;
	#endif
	reflectedLight.indirectSpecular += indirectSpecular;
	reflectedLight.indirectDiffuse += indirectDiffuse;
}
#define RE_Direct				RE_Direct_Physical
#define RE_Direct_RectArea		RE_Direct_RectArea_Physical
#define RE_IndirectDiffuse		RE_IndirectDiffuse_Physical
#define RE_IndirectSpecular		RE_IndirectSpecular_Physical
float computeSpecularOcclusion( const in float dotNV, const in float ambientOcclusion, const in float roughness ) {
	return saturate( pow( dotNV + ambientOcclusion, exp2( - 16.0 * roughness - 1.0 ) ) - 1.0 + ambientOcclusion );
}`,lights_fragment_begin:`
vec3 geometryPosition = - vViewPosition;
vec3 geometryNormal = normal;
vec3 geometryViewDir = ( isOrthographic ) ? vec3( 0, 0, 1 ) : normalize( vViewPosition );
vec3 geometryClearcoatNormal = vec3( 0.0 );
#ifdef USE_CLEARCOAT
	geometryClearcoatNormal = clearcoatNormal;
#endif
#ifdef USE_IRIDESCENCE
	float dotNVi = saturate( dot( normal, geometryViewDir ) );
	if ( material.iridescenceThickness == 0.0 ) {
		material.iridescence = 0.0;
	} else {
		material.iridescence = saturate( material.iridescence );
	}
	if ( material.iridescence > 0.0 ) {
		vec3 iridescenceFresnelDielectric = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.specularColor );
		vec3 iridescenceFresnelMetallic = evalIridescence( 1.0, material.iridescenceIOR, dotNVi, material.iridescenceThickness, material.diffuseColor );
		material.iridescenceFresnel = mix( iridescenceFresnelDielectric, iridescenceFresnelMetallic, material.metalness );
		material.iridescenceF0Dielectric = Schlick_to_F0( iridescenceFresnelDielectric, 1.0, dotNVi );
		material.iridescenceF0Metallic = Schlick_to_F0( iridescenceFresnelMetallic, 1.0, dotNVi );
	}
#endif
#ifdef STANDARD
	float dotNVms = saturate( dot( geometryNormal, geometryViewDir ) );
	material.dfg = texture2D( dfgLUT, vec2( material.roughness, dotNVms ) ).rg;
	#if ( NUM_SUN_LIGHTS > 0 || NUM_DIR_LIGHTS > 0 || NUM_POINT_LIGHTS > 0 || NUM_SPOT_LIGHTS > 0 )
		float EssMs = material.dfg.x + material.dfg.y;
		material.multiScatteringCompensation = 1.0 + material.specularColorBlended * ( 1.0 / EssMs - 1.0 );
	#endif
#endif
IncidentLight directLight;
#if ( NUM_POINT_LIGHTS > 0 ) && defined( RE_Direct )
	PointLight pointLight;
	#if defined( USE_SHADOWMAP ) && NUM_POINT_LIGHT_SHADOWS > 0
	PointLightShadow pointLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHTS; i ++ ) {
		pointLight = pointLights[ i ];
		getPointLightInfo( pointLight, geometryPosition, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_POINT_LIGHT_SHADOWS ) && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
		pointLightShadow = pointLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getPointShadow( pointShadowMap[ i ], pointLightShadow.shadowMapSize, pointLightShadow.shadowIntensity, pointLightShadow.shadowBias, pointLightShadow.shadowRadius, vPointShadowCoord[ i ], pointLightShadow.shadowCameraNear, pointLightShadow.shadowCameraFar ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_SPOT_LIGHTS > 0 ) && defined( RE_Direct )
	SpotLight spotLight;
	vec4 spotColor;
	vec3 spotLightCoord;
	bool inSpotLightMap;
	#if defined( USE_SHADOWMAP ) && NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHTS; i ++ ) {
		spotLight = spotLights[ i ];
		getSpotLightInfo( spotLight, geometryPosition, directLight );
		#if ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#define SPOT_LIGHT_MAP_INDEX UNROLLED_LOOP_INDEX
		#elif ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		#define SPOT_LIGHT_MAP_INDEX NUM_SPOT_LIGHT_MAPS
		#else
		#define SPOT_LIGHT_MAP_INDEX ( UNROLLED_LOOP_INDEX - NUM_SPOT_LIGHT_SHADOWS + NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS )
		#endif
		#if ( SPOT_LIGHT_MAP_INDEX < NUM_SPOT_LIGHT_MAPS )
			spotLightCoord = vSpotLightCoord[ i ].xyz / vSpotLightCoord[ i ].w;
			inSpotLightMap = all( lessThan( abs( spotLightCoord * 2. - 1. ), vec3( 1.0 ) ) );
			spotColor = texture2D( spotLightMap[ SPOT_LIGHT_MAP_INDEX ], spotLightCoord.xy );
			directLight.color = inSpotLightMap ? directLight.color * spotColor.rgb : directLight.color;
		#endif
		#undef SPOT_LIGHT_MAP_INDEX
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
		spotLightShadow = spotLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( spotShadowMap[ i ], spotLightShadow.shadowMapSize, spotLightShadow.shadowIntensity, spotLightShadow.shadowBias, spotLightShadow.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_SUN_LIGHTS > 0 ) && defined( RE_Direct )
	SunLight sunLight;
	#if defined( USE_SHADOWMAP ) && NUM_SUN_LIGHT_SHADOWS > 0
	SunLightShadow sunLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SUN_LIGHTS; i ++ ) {
		sunLight = sunLights[ i ];
		getSunLightInfo( sunLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_SUN_LIGHT_SHADOWS )
		sunLightShadow = sunLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getSunShadow( sunShadowMap[ i ], sunLightShadow, UNROLLED_LOOP_INDEX ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_DIR_LIGHTS > 0 ) && defined( RE_Direct )
	DirectionalLight directionalLight;
	#if defined( USE_SHADOWMAP ) && NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLightShadow;
	#endif
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHTS; i ++ ) {
		directionalLight = directionalLights[ i ];
		getDirectionalLightInfo( directionalLight, directLight );
		#if defined( USE_SHADOWMAP ) && ( UNROLLED_LOOP_INDEX < NUM_DIR_LIGHT_SHADOWS )
		directionalLightShadow = directionalLightShadows[ i ];
		directLight.color *= ( directLight.visible && receiveShadow ) ? getShadow( directionalShadowMap[ i ], directionalLightShadow.shadowMapSize, directionalLightShadow.shadowIntensity, directionalLightShadow.shadowBias, directionalLightShadow.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
		#endif
		RE_Direct( directLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if ( NUM_RECT_AREA_LIGHTS > 0 ) && defined( RE_Direct_RectArea )
	RectAreaLight rectAreaLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_RECT_AREA_LIGHTS; i ++ ) {
		rectAreaLight = rectAreaLights[ i ];
		RE_Direct_RectArea( rectAreaLight, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
	}
	#pragma unroll_loop_end
#endif
#if defined( RE_IndirectDiffuse )
	vec3 iblIrradiance = vec3( 0.0 );
	vec3 irradiance = getAmbientLightIrradiance( ambientLightColor );
	#if defined( USE_LIGHT_PROBES )
		irradiance += getLightProbeIrradiance( lightProbe, geometryNormal );
	#endif
	#if ( NUM_HEMI_LIGHTS > 0 )
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_HEMI_LIGHTS; i ++ ) {
			irradiance += getHemisphereLightIrradiance( hemisphereLights[ i ], geometryNormal );
		}
		#pragma unroll_loop_end
	#endif
	#ifdef USE_LIGHT_PROBES_GRID
		vec3 probeWorldPos = ( ( vec4( geometryPosition, 1.0 ) - viewMatrix[ 3 ] ) * viewMatrix ).xyz;
		vec3 probeWorldNormal = transformNormalByInverseViewMatrix( geometryNormal, viewMatrix );
		irradiance += getLightProbeGridIrradiance( probeWorldPos, probeWorldNormal );
	#endif
#endif
#if defined( RE_IndirectSpecular )
	vec3 radiance = vec3( 0.0 );
	vec3 clearcoatRadiance = vec3( 0.0 );
#endif`,lights_fragment_maps:`#if defined( RE_IndirectDiffuse )
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		vec3 lightMapIrradiance = lightMapTexel.rgb * lightMapIntensity;
		irradiance += lightMapIrradiance;
	#endif
	#if defined( USE_ENVMAP ) && defined( ENVMAP_TYPE_CUBE_UV )
		#if defined( STANDARD ) || defined( LAMBERT ) || defined( PHONG )
			iblIrradiance += getIBLIrradiance( geometryNormal );
		#endif
	#endif
#endif
#if defined( USE_ENVMAP ) && defined( RE_IndirectSpecular )
	#ifdef USE_ANISOTROPY
		vec3 iblRadiance = getIBLAnisotropyRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
	#else
		vec3 iblRadiance = getIBLRadiance( geometryViewDir, geometryNormal, material.roughness );
	#endif
	#ifdef USE_RETROREFLECTION
		#ifdef USE_ANISOTROPY
			vec3 retroIBLRadiance = getIBLAnisotropyRetroRadiance( geometryViewDir, geometryNormal, material.roughness, material.anisotropyB, material.anisotropy );
		#else
			vec3 retroIBLRadiance = getIBLRetroRadiance( geometryViewDir, geometryNormal, material.roughness );
		#endif
		iblRadiance = mix( iblRadiance, retroIBLRadiance, saturate( material.retroreflectivity ) );
	#endif
	radiance += iblRadiance;
	#ifdef USE_CLEARCOAT
		clearcoatRadiance += getIBLRadiance( geometryViewDir, geometryClearcoatNormal, material.clearcoatRoughness );
	#endif
#endif`,lights_fragment_end:`#if defined( RE_IndirectDiffuse )
	#if defined( LAMBERT ) || defined( PHONG )
		irradiance += iblIrradiance;
	#endif
	RE_IndirectDiffuse( irradiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif
#if defined( RE_IndirectSpecular )
	RE_IndirectSpecular( radiance, iblIrradiance, clearcoatRadiance, geometryPosition, geometryNormal, geometryViewDir, geometryClearcoatNormal, material, reflectedLight );
#endif`,lightprobes_pars_fragment:`#ifdef USE_LIGHT_PROBES_GRID
uniform highp sampler3D probesSH;
uniform vec3 probesMin;
uniform vec3 probesMax;
uniform vec3 probesResolution;
vec3 getLightProbeGridIrradiance( vec3 worldPos, vec3 worldNormal ) {
	vec3 res = probesResolution;
	vec3 gridRange = probesMax - probesMin;
	vec3 resMinusOne = res - 1.0;
	vec3 probeSpacing = gridRange / resMinusOne;
	vec3 samplePos = worldPos + worldNormal * probeSpacing * 0.5;
	vec3 uvw = clamp( ( samplePos - probesMin ) / gridRange, 0.0, 1.0 );
	uvw = uvw * resMinusOne / res + 0.5 / res;
	float nz          = res.z;
	float paddedSlices = nz + 2.0;
	float atlasDepth  = 7.0 * paddedSlices;
	float uvZBase     = uvw.z * nz + 1.0;
	vec4 s0 = texture( probesSH, vec3( uvw.xy, ( uvZBase                       ) / atlasDepth ) );
	vec4 s1 = texture( probesSH, vec3( uvw.xy, ( uvZBase +       paddedSlices   ) / atlasDepth ) );
	vec4 s2 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 2.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s3 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 3.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s4 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 4.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s5 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 5.0 * paddedSlices   ) / atlasDepth ) );
	vec4 s6 = texture( probesSH, vec3( uvw.xy, ( uvZBase + 6.0 * paddedSlices   ) / atlasDepth ) );
	vec3 c0 = s0.xyz;
	vec3 c1 = vec3( s0.w, s1.xy );
	vec3 c2 = vec3( s1.zw, s2.x );
	vec3 c3 = s2.yzw;
	vec3 c4 = s3.xyz;
	vec3 c5 = vec3( s3.w, s4.xy );
	vec3 c6 = vec3( s4.zw, s5.x );
	vec3 c7 = s5.yzw;
	vec3 c8 = s6.xyz;
	float x = worldNormal.x, y = worldNormal.y, z = worldNormal.z;
	vec3 result = c0 * 0.886227;
	result += c1 * 2.0 * 0.511664 * y;
	result += c2 * 2.0 * 0.511664 * z;
	result += c3 * 2.0 * 0.511664 * x;
	result += c4 * 2.0 * 0.429043 * x * y;
	result += c5 * 2.0 * 0.429043 * y * z;
	result += c6 * ( 0.743125 * z * z - 0.247708 );
	result += c7 * 2.0 * 0.429043 * x * z;
	result += c8 * 0.429043 * ( x * x - y * y );
	return max( result, vec3( 0.0 ) );
}
#endif`,logdepthbuf_fragment:`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	gl_FragDepth = vIsPerspective == 0.0 ? gl_FragCoord.z : log2( vFragDepth ) * logDepthBufFC * 0.5;
#endif`,logdepthbuf_pars_fragment:`#if defined( USE_LOGARITHMIC_DEPTH_BUFFER )
	uniform float logDepthBufFC;
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,logdepthbuf_pars_vertex:`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	varying float vFragDepth;
	varying float vIsPerspective;
#endif`,logdepthbuf_vertex:`#ifdef USE_LOGARITHMIC_DEPTH_BUFFER
	vFragDepth = 1.0 + gl_Position.w;
	vIsPerspective = float( isPerspectiveMatrix( projectionMatrix ) );
#endif`,map_fragment:`#ifdef USE_MAP
	vec4 sampledDiffuseColor = texture2D( map, vMapUv );
	#ifdef DECODE_VIDEO_TEXTURE
		sampledDiffuseColor = sRGBTransferEOTF( sampledDiffuseColor );
	#endif
	diffuseColor *= sampledDiffuseColor;
#endif`,map_pars_fragment:`#ifdef USE_MAP
	uniform sampler2D map;
#endif`,map_particle_fragment:`#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
	#if defined( USE_POINTS_UV )
		vec2 uv = vUv;
	#else
		vec2 uv = ( uvTransform * vec3( gl_PointCoord.x, 1.0 - gl_PointCoord.y, 1 ) ).xy;
	#endif
#endif
#ifdef USE_MAP
	diffuseColor *= texture2D( map, uv );
#endif
#ifdef USE_ALPHAMAP
	diffuseColor.a *= texture2D( alphaMap, uv ).g;
#endif`,map_particle_pars_fragment:`#if defined( USE_POINTS_UV )
	varying vec2 vUv;
#else
	#if defined( USE_MAP ) || defined( USE_ALPHAMAP )
		uniform mat3 uvTransform;
	#endif
#endif
#ifdef USE_MAP
	uniform sampler2D map;
#endif
#ifdef USE_ALPHAMAP
	uniform sampler2D alphaMap;
#endif`,metalnessmap_fragment:`float metalnessFactor = metalness;
#ifdef USE_METALNESSMAP
	vec4 texelMetalness = texture2D( metalnessMap, vMetalnessMapUv );
	metalnessFactor *= texelMetalness.b;
#endif`,metalnessmap_pars_fragment:`#ifdef USE_METALNESSMAP
	uniform sampler2D metalnessMap;
#endif`,morphinstance_vertex:`#ifdef USE_INSTANCING_MORPH
	float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	float morphTargetBaseInfluence = texelFetch( morphTexture, ivec2( 0, gl_InstanceID ), 0 ).r;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		morphTargetInfluences[i] =  texelFetch( morphTexture, ivec2( i + 1, gl_InstanceID ), 0 ).r;
	}
#endif`,morphcolor_vertex:`#if defined( USE_MORPHCOLORS )
	vColor *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		#if defined( USE_COLOR_ALPHA )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ) * morphTargetInfluences[ i ];
		#elif defined( USE_COLOR )
			if ( morphTargetInfluences[ i ] != 0.0 ) vColor += getMorph( gl_VertexID, i, 2 ).rgb * morphTargetInfluences[ i ];
		#endif
	}
#endif`,morphnormal_vertex:`#ifdef USE_MORPHNORMALS
	objectNormal *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) objectNormal += getMorph( gl_VertexID, i, 1 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,morphtarget_pars_vertex:`#ifdef USE_MORPHTARGETS
	#ifndef USE_INSTANCING_MORPH
		uniform float morphTargetBaseInfluence;
		uniform float morphTargetInfluences[ MORPHTARGETS_COUNT ];
	#endif
	uniform sampler2DArray morphTargetsTexture;
	uniform ivec2 morphTargetsTextureSize;
	vec4 getMorph( const in int vertexIndex, const in int morphTargetIndex, const in int offset ) {
		int texelIndex = vertexIndex * MORPHTARGETS_TEXTURE_STRIDE + offset;
		int y = texelIndex / morphTargetsTextureSize.x;
		int x = texelIndex - y * morphTargetsTextureSize.x;
		ivec3 morphUV = ivec3( x, y, morphTargetIndex );
		return texelFetch( morphTargetsTexture, morphUV, 0 );
	}
#endif`,morphtarget_vertex:`#ifdef USE_MORPHTARGETS
	transformed *= morphTargetBaseInfluence;
	for ( int i = 0; i < MORPHTARGETS_COUNT; i ++ ) {
		if ( morphTargetInfluences[ i ] != 0.0 ) transformed += getMorph( gl_VertexID, i, 0 ).xyz * morphTargetInfluences[ i ];
	}
#endif`,normal_fragment_begin:`float faceDirection = gl_FrontFacing ? 1.0 : - 1.0;
#ifdef FLAT_SHADED
	vec3 fdx = dFdx( vViewPosition );
	vec3 fdy = dFdy( vViewPosition );
	vec3 normal = normalize( cross( fdx, fdy ) );
#else
	vec3 normal = normalize( vNormal );
	#ifdef DOUBLE_SIDED
		normal *= faceDirection;
	#endif
#endif
#if defined( USE_NORMALMAP_TANGENTSPACE ) || defined( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY )
	#ifdef USE_TANGENT
		mat3 tbn = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn = getTangentFrame( - vViewPosition, normal,
		#if defined( USE_NORMALMAP )
			vNormalMapUv
		#elif defined( USE_CLEARCOAT_NORMALMAP )
			vClearcoatNormalMapUv
		#else
			vUv
		#endif
		);
	#endif
	#ifdef DOUBLE_SIDED
		tbn[0] *= faceDirection;
		tbn[1] *= faceDirection;
	#endif
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	#ifdef USE_TANGENT
		mat3 tbn2 = mat3( normalize( vTangent ), normalize( vBitangent ), normal );
	#else
		mat3 tbn2 = getTangentFrame( - vViewPosition, normal, vClearcoatNormalMapUv );
	#endif
	#ifdef DOUBLE_SIDED
		tbn2[0] *= faceDirection;
		tbn2[1] *= faceDirection;
	#endif
#endif
vec3 nonPerturbedNormal = normal;`,normal_fragment_maps:`#ifdef USE_NORMALMAP_OBJECTSPACE
	normal = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#ifdef FLIP_SIDED
		normal = - normal;
	#endif
	#ifdef DOUBLE_SIDED
		normal = normal * faceDirection;
	#endif
	normal = normalize( normalMatrix * normal );
#elif defined( USE_NORMALMAP_TANGENTSPACE )
	vec3 mapN = texture2D( normalMap, vNormalMapUv ).xyz * 2.0 - 1.0;
	#if defined( USE_PACKED_NORMALMAP )
		mapN = vec3( mapN.xy, sqrt( saturate( 1.0 - dot( mapN.xy, mapN.xy ) ) ) );
	#endif
	mapN.xy *= normalScale;
	normal = normalize( tbn * mapN );
#elif defined( USE_BUMPMAP )
	normal = perturbNormalArb( - vViewPosition, normal, dHdxy_fwd(), faceDirection );
#endif`,normal_pars_fragment:`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,normal_pars_vertex:`#ifndef FLAT_SHADED
	varying vec3 vNormal;
	#ifdef USE_TANGENT
		varying vec3 vTangent;
		varying vec3 vBitangent;
	#endif
#endif`,normal_vertex:`#ifndef FLAT_SHADED
	vNormal = normalize( transformedNormal );
	#ifdef USE_TANGENT
		vTangent = normalize( transformedTangent );
		vBitangent = normalize( cross( vNormal, vTangent ) * tangent.w );
		#ifdef FLIP_SIDED
			vBitangent = - vBitangent;
		#endif
	#endif
#endif`,normalmap_pars_fragment:`#ifdef USE_NORMALMAP
	uniform sampler2D normalMap;
	uniform vec2 normalScale;
#endif
#ifdef USE_NORMALMAP_OBJECTSPACE
	uniform mat3 normalMatrix;
#endif
#if ! defined ( USE_TANGENT ) && ( defined ( USE_NORMALMAP_TANGENTSPACE ) || defined ( USE_CLEARCOAT_NORMALMAP ) || defined( USE_ANISOTROPY ) )
	mat3 getTangentFrame( vec3 eye_pos, vec3 surf_norm, vec2 uv ) {
		vec3 q0 = dFdx( eye_pos.xyz );
		vec3 q1 = dFdy( eye_pos.xyz );
		vec2 st0 = dFdx( uv.st );
		vec2 st1 = dFdy( uv.st );
		vec3 N = surf_norm;
		vec3 q1perp = cross( q1, N );
		vec3 q0perp = cross( N, q0 );
		vec3 T = q1perp * st0.x + q0perp * st1.x;
		vec3 B = q1perp * st0.y + q0perp * st1.y;
		float det = max( dot( T, T ), dot( B, B ) );
		float scale = ( det == 0.0 ) ? 0.0 : inversesqrt( det );
		return mat3( T * scale, B * scale, N );
	}
#endif`,clearcoat_normal_fragment_begin:`#ifdef USE_CLEARCOAT
	vec3 clearcoatNormal = nonPerturbedNormal;
#endif`,clearcoat_normal_fragment_maps:`#ifdef USE_CLEARCOAT_NORMALMAP
	vec3 clearcoatMapN = texture2D( clearcoatNormalMap, vClearcoatNormalMapUv ).xyz * 2.0 - 1.0;
	clearcoatMapN.xy *= clearcoatNormalScale;
	clearcoatNormal = normalize( tbn2 * clearcoatMapN );
#endif`,clearcoat_pars_fragment:`#ifdef USE_CLEARCOATMAP
	uniform sampler2D clearcoatMap;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform sampler2D clearcoatNormalMap;
	uniform vec2 clearcoatNormalScale;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform sampler2D clearcoatRoughnessMap;
#endif`,iridescence_pars_fragment:`#ifdef USE_IRIDESCENCEMAP
	uniform sampler2D iridescenceMap;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform sampler2D iridescenceThicknessMap;
#endif`,opaque_fragment:`#ifdef OPAQUE
diffuseColor.a = 1.0;
#endif
#ifdef USE_TRANSMISSION
diffuseColor.a *= material.transmissionAlpha;
#endif
gl_FragColor = vec4( outgoingLight, diffuseColor.a );`,packing:`vec3 packNormalToRGB( const in vec3 normal ) {
	return normalize( normal ) * 0.5 + 0.5;
}
vec3 unpackRGBToNormal( const in vec3 rgb ) {
	return 2.0 * rgb.xyz - 1.0;
}
const float PackUpscale = 256. / 255.;const float UnpackDownscale = 255. / 256.;const float ShiftRight8 = 1. / 256.;
const float Inv255 = 1. / 255.;
const vec4 PackFactors = vec4( 1.0, 256.0, 256.0 * 256.0, 256.0 * 256.0 * 256.0 );
const vec2 UnpackFactors2 = vec2( UnpackDownscale, 1.0 / PackFactors.g );
const vec3 UnpackFactors3 = vec3( UnpackDownscale / PackFactors.rg, 1.0 / PackFactors.b );
const vec4 UnpackFactors4 = vec4( UnpackDownscale / PackFactors.rgb, 1.0 / PackFactors.a );
vec4 packDepthToRGBA( const in float v ) {
	if( v <= 0.0 )
		return vec4( 0., 0., 0., 0. );
	if( v >= 1.0 )
		return vec4( 1., 1., 1., 1. );
	float vuf;
	float af = modf( v * PackFactors.a, vuf );
	float bf = modf( vuf * ShiftRight8, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec4( vuf * Inv255, gf * PackUpscale, bf * PackUpscale, af );
}
vec3 packDepthToRGB( const in float v ) {
	if( v <= 0.0 )
		return vec3( 0., 0., 0. );
	if( v >= 1.0 )
		return vec3( 1., 1., 1. );
	float vuf;
	float bf = modf( v * PackFactors.b, vuf );
	float gf = modf( vuf * ShiftRight8, vuf );
	return vec3( vuf * Inv255, gf * PackUpscale, bf );
}
vec2 packDepthToRG( const in float v ) {
	if( v <= 0.0 )
		return vec2( 0., 0. );
	if( v >= 1.0 )
		return vec2( 1., 1. );
	float vuf;
	float gf = modf( v * 256., vuf );
	return vec2( vuf * Inv255, gf );
}
float unpackRGBAToDepth( const in vec4 v ) {
	return dot( v, UnpackFactors4 );
}
float unpackRGBToDepth( const in vec3 v ) {
	return dot( v, UnpackFactors3 );
}
float unpackRGToDepth( const in vec2 v ) {
	return v.r * UnpackFactors2.r + v.g * UnpackFactors2.g;
}
vec4 pack2HalfToRGBA( const in vec2 v ) {
	vec4 r = vec4( v.x, fract( v.x * 255.0 ), v.y, fract( v.y * 255.0 ) );
	return vec4( r.x - r.y / 255.0, r.y, r.z - r.w / 255.0, r.w );
}
vec2 unpackRGBATo2Half( const in vec4 v ) {
	return vec2( v.x + ( v.y / 255.0 ), v.z + ( v.w / 255.0 ) );
}
float viewZToOrthographicDepth( const in float viewZ, const in float near, const in float far ) {
	return ( viewZ + near ) / ( near - far );
}
float orthographicDepthToViewZ( const in float depth, const in float near, const in float far ) {
	#ifdef USE_REVERSED_DEPTH_BUFFER
	
		return depth * ( far - near ) - far;
	#else
		return depth * ( near - far ) - near;
	#endif
}
float viewZToPerspectiveDepth( const in float viewZ, const in float near, const in float far ) {
	return ( ( near + viewZ ) * far ) / ( ( far - near ) * viewZ );
}
float perspectiveDepthToViewZ( const in float depth, const in float near, const in float far ) {
	
	#ifdef USE_REVERSED_DEPTH_BUFFER
		return ( near * far ) / ( ( near - far ) * depth - near );
	#else
		return ( near * far ) / ( ( far - near ) * depth - far );
	#endif
}`,premultiplied_alpha_fragment:`#ifdef PREMULTIPLIED_ALPHA
	gl_FragColor.rgb *= gl_FragColor.a;
#endif`,project_vertex:`vec4 mvPosition = vec4( transformed, 1.0 );
#ifdef USE_BATCHING
	mvPosition = batchingMatrix * mvPosition;
#endif
#ifdef USE_INSTANCING
	mvPosition = instanceMatrix * mvPosition;
#endif
mvPosition = modelViewMatrix * mvPosition;
gl_Position = projectionMatrix * mvPosition;`,dithering_fragment:`#ifdef DITHERING
	gl_FragColor.rgb = dithering( gl_FragColor.rgb );
#endif`,dithering_pars_fragment:`#ifdef DITHERING
	vec3 dithering( vec3 color ) {
		float grid_position = rand( gl_FragCoord.xy );
		vec3 dither_shift_RGB = vec3( 0.25 / 255.0, -0.25 / 255.0, 0.25 / 255.0 );
		dither_shift_RGB = mix( 2.0 * dither_shift_RGB, -2.0 * dither_shift_RGB, grid_position );
		return color + dither_shift_RGB;
	}
#endif`,roughnessmap_fragment:`float roughnessFactor = roughness;
#ifdef USE_ROUGHNESSMAP
	vec4 texelRoughness = texture2D( roughnessMap, vRoughnessMapUv );
	roughnessFactor *= texelRoughness.g;
#endif`,roughnessmap_pars_fragment:`#ifdef USE_ROUGHNESSMAP
	uniform sampler2D roughnessMap;
#endif`,shadowmap_pars_fragment:`#if NUM_SPOT_LIGHT_COORDS > 0
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#if NUM_SPOT_LIGHT_MAPS > 0
	uniform sampler2D spotLightMap[ NUM_SPOT_LIGHT_MAPS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
		#define SUN_LIGHT_CASCADES 2
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow sunShadowMap[ NUM_SUN_LIGHT_SHADOWS ];
		#else
			uniform sampler2D sunShadowMap[ NUM_SUN_LIGHT_SHADOWS ];
		#endif
		uniform mat4 sunShadowMatrix[ NUM_SUN_LIGHT_SHADOWS * SUN_LIGHT_CASCADES ];
		uniform vec4 sunShadowCascade[ NUM_SUN_LIGHT_SHADOWS * SUN_LIGHT_CASCADES ];
		varying vec4 vSunShadowWorldPosition;
		varying vec3 vSunShadowWorldNormal;
		struct SunLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SunLightShadow sunLightShadows[ NUM_SUN_LIGHT_SHADOWS ];
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#else
			uniform sampler2D directionalShadowMap[ NUM_DIR_LIGHT_SHADOWS ];
		#endif
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform sampler2DShadow spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#else
			uniform sampler2D spotShadowMap[ NUM_SPOT_LIGHT_SHADOWS ];
		#endif
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#if defined( SHADOWMAP_TYPE_PCF )
			uniform samplerCubeShadow pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#elif defined( SHADOWMAP_TYPE_BASIC )
			uniform samplerCube pointShadowMap[ NUM_POINT_LIGHT_SHADOWS ];
		#endif
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float interleavedGradientNoise( vec2 position ) {
			return fract( 52.9829189 * fract( dot( position, vec2( 0.06711056, 0.00583715 ) ) ) );
		}
		vec2 vogelDiskSample( int sampleIndex, int samplesCount, float phi ) {
			const float goldenAngle = 2.399963229728653;
			float r = sqrt( ( float( sampleIndex ) + 0.5 ) / float( samplesCount ) );
			float theta = float( sampleIndex ) * goldenAngle + phi;
			return vec2( cos( theta ), sin( theta ) ) * r;
		}
	#endif
	#if defined( SHADOWMAP_TYPE_PCF )
		float getShadow( sampler2DShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			shadowCoord.z += shadowBias;
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 texelSize = vec2( 1.0 ) / shadowMapSize;
				float radius = shadowRadius * texelSize.x;
				float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
				shadow = (
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 0, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 1, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 2, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 3, 5, phi ) * radius, shadowCoord.z ) ) +
					texture( shadowMap, vec3( shadowCoord.xy + vogelDiskSample( 4, 5, phi ) * radius, shadowCoord.z ) )
				) * 0.2;
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#elif defined( SHADOWMAP_TYPE_VSM )
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				vec2 distribution = texture2D( shadowMap, shadowCoord.xy ).rg;
				float mean = distribution.x;
				float variance = distribution.y * distribution.y;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					float hard_shadow = step( mean, shadowCoord.z );
				#else
					float hard_shadow = step( shadowCoord.z, mean );
				#endif
				
				if ( hard_shadow == 1.0 ) {
					shadow = 1.0;
				} else {
					variance = max( variance, 0.0000001 );
					float d = shadowCoord.z - mean;
					float p_max = variance / ( variance + d * d );
					p_max = clamp( ( p_max - 0.3 ) / 0.65, 0.0, 1.0 );
					shadow = max( hard_shadow, p_max );
				}
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#else
		float getShadow( sampler2D shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord ) {
			float shadow = 1.0;
			shadowCoord.xyz /= shadowCoord.w;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				shadowCoord.z -= shadowBias;
			#else
				shadowCoord.z += shadowBias;
			#endif
			bool inFrustum = shadowCoord.x >= 0.0 && shadowCoord.x <= 1.0 && shadowCoord.y >= 0.0 && shadowCoord.y <= 1.0;
			bool frustumTest = inFrustum && shadowCoord.z <= 1.0;
			if ( frustumTest ) {
				float depth = texture2D( shadowMap, shadowCoord.xy ).r;
				#ifdef USE_REVERSED_DEPTH_BUFFER
					shadow = step( depth, shadowCoord.z );
				#else
					shadow = step( shadowCoord.z, depth );
				#endif
			}
			return mix( 1.0, shadow, shadowIntensity );
		}
	#endif
	#if NUM_SUN_LIGHT_SHADOWS > 0
		float getSunShadow(
			#if defined( SHADOWMAP_TYPE_PCF )
				sampler2DShadow shadowMap,
			#else
				sampler2D shadowMap,
			#endif
			SunLightShadow sunLightShadow,
			int shadowIndex
		) {
			vec4 shadowWorldPosition = vec4( vSunShadowWorldPosition.xyz + vSunShadowWorldNormal * sunLightShadow.shadowNormalBias, 1.0 );
			float viewDepth = vSunShadowWorldPosition.w;
			int cascadeOffset = shadowIndex * SUN_LIGHT_CASCADES;
			float shadow = 1.0;
			for ( int i = SUN_LIGHT_CASCADES - 1; i >= 0; i -- ) {
				vec4 cascade = sunShadowCascade[ cascadeOffset + i ];
				if ( viewDepth >= cascade.x && viewDepth < cascade.y ) {
					float cascadeShadow = getShadow(
						shadowMap,
						sunLightShadow.shadowMapSize,
						sunLightShadow.shadowIntensity,
						sunLightShadow.shadowBias,
						sunLightShadow.shadowRadius,
						sunShadowMatrix[ cascadeOffset + i ] * shadowWorldPosition
					);
					shadow = mix( cascadeShadow, shadow, smoothstep( cascade.z, cascade.y, viewDepth ) );
				}
			}
			return shadow;
		}
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
	#if defined( SHADOWMAP_TYPE_PCF )
	float getPointShadow( samplerCubeShadow shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 bd3D = normalize( lightToPosition );
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			#ifdef USE_REVERSED_DEPTH_BUFFER
				float dp = ( shadowCameraNear * ( shadowCameraFar - viewSpaceZ ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp -= shadowBias;
			#else
				float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
				dp += shadowBias;
			#endif
			float texelSize = shadowRadius / shadowMapSize.x;
			vec3 absDir = abs( bd3D );
			vec3 tangent = absDir.x > absDir.z ? vec3( 0.0, 1.0, 0.0 ) : vec3( 1.0, 0.0, 0.0 );
			tangent = normalize( cross( bd3D, tangent ) );
			vec3 bitangent = cross( bd3D, tangent );
			float phi = interleavedGradientNoise( gl_FragCoord.xy ) * PI2;
			vec2 sample0 = vogelDiskSample( 0, 5, phi );
			vec2 sample1 = vogelDiskSample( 1, 5, phi );
			vec2 sample2 = vogelDiskSample( 2, 5, phi );
			vec2 sample3 = vogelDiskSample( 3, 5, phi );
			vec2 sample4 = vogelDiskSample( 4, 5, phi );
			shadow = (
				texture( shadowMap, vec4( bd3D + ( tangent * sample0.x + bitangent * sample0.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample1.x + bitangent * sample1.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample2.x + bitangent * sample2.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample3.x + bitangent * sample3.y ) * texelSize, dp ) ) +
				texture( shadowMap, vec4( bd3D + ( tangent * sample4.x + bitangent * sample4.y ) * texelSize, dp ) )
			) * 0.2;
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#elif defined( SHADOWMAP_TYPE_BASIC )
	float getPointShadow( samplerCube shadowMap, vec2 shadowMapSize, float shadowIntensity, float shadowBias, float shadowRadius, vec4 shadowCoord, float shadowCameraNear, float shadowCameraFar ) {
		float shadow = 1.0;
		vec3 lightToPosition = shadowCoord.xyz;
		vec3 absVec = abs( lightToPosition );
		float viewSpaceZ = max( max( absVec.x, absVec.y ), absVec.z );
		if ( viewSpaceZ - shadowCameraFar <= 0.0 && viewSpaceZ - shadowCameraNear >= 0.0 ) {
			float dp = ( shadowCameraFar * ( viewSpaceZ - shadowCameraNear ) ) / ( viewSpaceZ * ( shadowCameraFar - shadowCameraNear ) );
			dp += shadowBias;
			vec3 bd3D = normalize( lightToPosition );
			float depth = textureCube( shadowMap, bd3D ).r;
			#ifdef USE_REVERSED_DEPTH_BUFFER
				depth = 1.0 - depth;
			#endif
			shadow = step( dp, depth );
		}
		return mix( 1.0, shadow, shadowIntensity );
	}
	#endif
	#endif
#endif`,shadowmap_pars_vertex:`#if NUM_SPOT_LIGHT_COORDS > 0
	uniform mat4 spotLightMatrix[ NUM_SPOT_LIGHT_COORDS ];
	varying vec4 vSpotLightCoord[ NUM_SPOT_LIGHT_COORDS ];
#endif
#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
		varying vec4 vSunShadowWorldPosition;
		varying vec3 vSunShadowWorldNormal;
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
		uniform mat4 directionalShadowMatrix[ NUM_DIR_LIGHT_SHADOWS ];
		varying vec4 vDirectionalShadowCoord[ NUM_DIR_LIGHT_SHADOWS ];
		struct DirectionalLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform DirectionalLightShadow directionalLightShadows[ NUM_DIR_LIGHT_SHADOWS ];
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
		struct SpotLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
		};
		uniform SpotLightShadow spotLightShadows[ NUM_SPOT_LIGHT_SHADOWS ];
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		uniform mat4 pointShadowMatrix[ NUM_POINT_LIGHT_SHADOWS ];
		varying vec4 vPointShadowCoord[ NUM_POINT_LIGHT_SHADOWS ];
		struct PointLightShadow {
			float shadowIntensity;
			float shadowBias;
			float shadowNormalBias;
			float shadowRadius;
			vec2 shadowMapSize;
			float shadowCameraNear;
			float shadowCameraFar;
		};
		uniform PointLightShadow pointLightShadows[ NUM_POINT_LIGHT_SHADOWS ];
	#endif
#endif`,shadowmap_vertex:`#if ( defined( USE_SHADOWMAP ) && ( NUM_DIR_LIGHT_SHADOWS > 0 || NUM_SUN_LIGHT_SHADOWS > 0 || NUM_POINT_LIGHT_SHADOWS > 0 ) ) || ( NUM_SPOT_LIGHT_COORDS > 0 )
	#ifdef HAS_NORMAL
		vec3 shadowWorldNormal = transformNormalByInverseViewMatrix( transformedNormal, viewMatrix );
	#else
		vec3 shadowWorldNormal = vec3( 0.0 );
	#endif
	vec4 shadowWorldPosition;
#endif
#if defined( USE_SHADOWMAP )
	#if NUM_SUN_LIGHT_SHADOWS > 0
		vSunShadowWorldPosition = vec4( worldPosition.xyz, - mvPosition.z );
		vSunShadowWorldNormal = shadowWorldNormal;
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * directionalLightShadows[ i ].shadowNormalBias, 0 );
			vDirectionalShadowCoord[ i ] = directionalShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0
		#pragma unroll_loop_start
		for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
			shadowWorldPosition = worldPosition + vec4( shadowWorldNormal * pointLightShadows[ i ].shadowNormalBias, 0 );
			vPointShadowCoord[ i ] = pointShadowMatrix[ i ] * shadowWorldPosition;
		}
		#pragma unroll_loop_end
	#endif
#endif
#if NUM_SPOT_LIGHT_COORDS > 0
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_COORDS; i ++ ) {
		shadowWorldPosition = worldPosition;
		#if ( defined( USE_SHADOWMAP ) && UNROLLED_LOOP_INDEX < NUM_SPOT_LIGHT_SHADOWS )
			shadowWorldPosition.xyz += shadowWorldNormal * spotLightShadows[ i ].shadowNormalBias;
		#endif
		vSpotLightCoord[ i ] = spotLightMatrix[ i ] * shadowWorldPosition;
	}
	#pragma unroll_loop_end
#endif`,shadowmask_pars_fragment:`float getShadowMask() {
	float shadow = 1.0;
	#ifdef USE_SHADOWMAP
	#if NUM_SUN_LIGHT_SHADOWS > 0
	SunLightShadow sunLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SUN_LIGHT_SHADOWS; i ++ ) {
		sunLight = sunLightShadows[ i ];
		shadow *= receiveShadow ? getSunShadow( sunShadowMap[ i ], sunLight, UNROLLED_LOOP_INDEX ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_DIR_LIGHT_SHADOWS > 0
	DirectionalLightShadow directionalLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_DIR_LIGHT_SHADOWS; i ++ ) {
		directionalLight = directionalLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( directionalShadowMap[ i ], directionalLight.shadowMapSize, directionalLight.shadowIntensity, directionalLight.shadowBias, directionalLight.shadowRadius, vDirectionalShadowCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_SPOT_LIGHT_SHADOWS > 0
	SpotLightShadow spotLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_SPOT_LIGHT_SHADOWS; i ++ ) {
		spotLight = spotLightShadows[ i ];
		shadow *= receiveShadow ? getShadow( spotShadowMap[ i ], spotLight.shadowMapSize, spotLight.shadowIntensity, spotLight.shadowBias, spotLight.shadowRadius, vSpotLightCoord[ i ] ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#if NUM_POINT_LIGHT_SHADOWS > 0 && ( defined( SHADOWMAP_TYPE_PCF ) || defined( SHADOWMAP_TYPE_BASIC ) )
	PointLightShadow pointLight;
	#pragma unroll_loop_start
	for ( int i = 0; i < NUM_POINT_LIGHT_SHADOWS; i ++ ) {
		pointLight = pointLightShadows[ i ];
		shadow *= receiveShadow ? getPointShadow( pointShadowMap[ i ], pointLight.shadowMapSize, pointLight.shadowIntensity, pointLight.shadowBias, pointLight.shadowRadius, vPointShadowCoord[ i ], pointLight.shadowCameraNear, pointLight.shadowCameraFar ) : 1.0;
	}
	#pragma unroll_loop_end
	#endif
	#endif
	return shadow;
}`,skinbase_vertex:`#ifdef USE_SKINNING
	mat4 boneMatX = getBoneMatrix( skinIndex.x );
	mat4 boneMatY = getBoneMatrix( skinIndex.y );
	mat4 boneMatZ = getBoneMatrix( skinIndex.z );
	mat4 boneMatW = getBoneMatrix( skinIndex.w );
#endif`,skinning_pars_vertex:`#ifdef USE_SKINNING
	uniform mat4 bindMatrix;
	uniform mat4 bindMatrixInverse;
	uniform highp sampler2D boneTexture;
	mat4 getBoneMatrix( const in float i ) {
		int size = textureSize( boneTexture, 0 ).x;
		int j = int( i ) * 4;
		int x = j % size;
		int y = j / size;
		vec4 v1 = texelFetch( boneTexture, ivec2( x, y ), 0 );
		vec4 v2 = texelFetch( boneTexture, ivec2( x + 1, y ), 0 );
		vec4 v3 = texelFetch( boneTexture, ivec2( x + 2, y ), 0 );
		vec4 v4 = texelFetch( boneTexture, ivec2( x + 3, y ), 0 );
		return mat4( v1, v2, v3, v4 );
	}
#endif`,skinning_vertex:`#ifdef USE_SKINNING
	vec4 skinVertex = bindMatrix * vec4( transformed, 1.0 );
	vec4 skinned = vec4( 0.0 );
	skinned += boneMatX * skinVertex * skinWeight.x;
	skinned += boneMatY * skinVertex * skinWeight.y;
	skinned += boneMatZ * skinVertex * skinWeight.z;
	skinned += boneMatW * skinVertex * skinWeight.w;
	transformed = ( bindMatrixInverse * skinned ).xyz;
#endif`,skinnormal_vertex:`#ifdef USE_SKINNING
	mat4 skinMatrix = mat4( 0.0 );
	skinMatrix += skinWeight.x * boneMatX;
	skinMatrix += skinWeight.y * boneMatY;
	skinMatrix += skinWeight.z * boneMatZ;
	skinMatrix += skinWeight.w * boneMatW;
	skinMatrix = bindMatrixInverse * skinMatrix * bindMatrix;
	objectNormal = vec4( skinMatrix * vec4( objectNormal, 0.0 ) ).xyz;
	#ifdef USE_TANGENT
		objectTangent = vec4( skinMatrix * vec4( objectTangent, 0.0 ) ).xyz;
	#endif
#endif`,specularmap_fragment:`float specularStrength;
#ifdef USE_SPECULARMAP
	vec4 texelSpecular = texture2D( specularMap, vSpecularMapUv );
	specularStrength = texelSpecular.r;
#else
	specularStrength = 1.0;
#endif`,specularmap_pars_fragment:`#ifdef USE_SPECULARMAP
	uniform sampler2D specularMap;
#endif`,tonemapping_fragment:`#if defined( TONE_MAPPING )
	gl_FragColor.rgb = toneMapping( gl_FragColor.rgb );
#endif`,tonemapping_pars_fragment:`#ifndef saturate
#define saturate( a ) clamp( a, 0.0, 1.0 )
#endif
uniform float toneMappingExposure;
vec3 LinearToneMapping( vec3 color ) {
	return saturate( toneMappingExposure * color );
}
vec3 ReinhardToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	return saturate( color / ( vec3( 1.0 ) + color ) );
}
vec3 CineonToneMapping( vec3 color ) {
	color *= toneMappingExposure;
	color = max( vec3( 0.0 ), color - 0.004 );
	return pow( ( color * ( 6.2 * color + 0.5 ) ) / ( color * ( 6.2 * color + 1.7 ) + 0.06 ), vec3( 2.2 ) );
}
vec3 RRTAndODTFit( vec3 v ) {
	vec3 a = v * ( v + 0.0245786 ) - 0.000090537;
	vec3 b = v * ( 0.983729 * v + 0.4329510 ) + 0.238081;
	return a / b;
}
vec3 ACESFilmicToneMapping( vec3 color ) {
	const mat3 ACESInputMat = mat3(
		vec3( 0.59719, 0.07600, 0.02840 ),		vec3( 0.35458, 0.90834, 0.13383 ),
		vec3( 0.04823, 0.01566, 0.83777 )
	);
	const mat3 ACESOutputMat = mat3(
		vec3(  1.60475, -0.10208, -0.00327 ),		vec3( -0.53108,  1.10813, -0.07276 ),
		vec3( -0.07367, -0.00605,  1.07602 )
	);
	color *= toneMappingExposure / 0.6;
	color = ACESInputMat * color;
	color = RRTAndODTFit( color );
	color = ACESOutputMat * color;
	return saturate( color );
}
const mat3 LINEAR_REC2020_TO_LINEAR_SRGB = mat3(
	vec3( 1.6605, - 0.1246, - 0.0182 ),
	vec3( - 0.5876, 1.1329, - 0.1006 ),
	vec3( - 0.0728, - 0.0083, 1.1187 )
);
const mat3 LINEAR_SRGB_TO_LINEAR_REC2020 = mat3(
	vec3( 0.6274, 0.0691, 0.0164 ),
	vec3( 0.3293, 0.9195, 0.0880 ),
	vec3( 0.0433, 0.0113, 0.8956 )
);
vec3 agxDefaultContrastApprox( vec3 x ) {
	vec3 x2 = x * x;
	vec3 x4 = x2 * x2;
	return + 15.5 * x4 * x2
		- 40.14 * x4 * x
		+ 31.96 * x4
		- 6.868 * x2 * x
		+ 0.4298 * x2
		+ 0.1191 * x
		- 0.00232;
}
vec3 AgXToneMapping( vec3 color ) {
	const mat3 AgXInsetMatrix = mat3(
		vec3( 0.856627153315983, 0.137318972929847, 0.11189821299995 ),
		vec3( 0.0951212405381588, 0.761241990602591, 0.0767994186031903 ),
		vec3( 0.0482516061458583, 0.101439036467562, 0.811302368396859 )
	);
	const mat3 AgXOutsetMatrix = mat3(
		vec3( 1.1271005818144368, - 0.1413297634984383, - 0.14132976349843826 ),
		vec3( - 0.11060664309660323, 1.157823702216272, - 0.11060664309660294 ),
		vec3( - 0.016493938717834573, - 0.016493938717834257, 1.2519364065950405 )
	);
	const float AgxMinEv = - 12.47393;	const float AgxMaxEv = 4.026069;
	color *= toneMappingExposure;
	color = LINEAR_SRGB_TO_LINEAR_REC2020 * color;
	color = AgXInsetMatrix * color;
	color = max( color, 1e-10 );	color = log2( color );
	color = ( color - AgxMinEv ) / ( AgxMaxEv - AgxMinEv );
	color = clamp( color, 0.0, 1.0 );
	color = agxDefaultContrastApprox( color );
	color = AgXOutsetMatrix * color;
	color = pow( max( vec3( 0.0 ), color ), vec3( 2.2 ) );
	color = LINEAR_REC2020_TO_LINEAR_SRGB * color;
	color = clamp( color, 0.0, 1.0 );
	return color;
}
vec3 NeutralToneMapping( vec3 color ) {
	const float StartCompression = 0.8 - 0.04;
	const float Desaturation = 0.15;
	color *= toneMappingExposure;
	float x = min( color.r, min( color.g, color.b ) );
	float offset = x < 0.08 ? x - 6.25 * x * x : 0.04;
	color -= offset;
	float peak = max( color.r, max( color.g, color.b ) );
	if ( peak < StartCompression ) return color;
	float d = 1. - StartCompression;
	float newPeak = 1. - d * d / ( peak + d - StartCompression );
	color *= newPeak / peak;
	float g = 1. - 1. / ( Desaturation * ( peak - newPeak ) + 1. );
	return mix( color, vec3( newPeak ), g );
}
vec3 CustomToneMapping( vec3 color ) { return color; }`,transmission_fragment:`#ifdef USE_TRANSMISSION
	material.transmission = transmission;
	material.transmissionAlpha = 1.0;
	material.thickness = thickness;
	material.attenuationDistance = attenuationDistance;
	material.attenuationColor = attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		material.transmission *= texture2D( transmissionMap, vTransmissionMapUv ).r;
	#endif
	#ifdef USE_THICKNESSMAP
		material.thickness *= texture2D( thicknessMap, vThicknessMapUv ).g;
	#endif
	vec3 pos = vWorldPosition;
	vec3 v = normalize( cameraPosition - pos );
	vec3 n = transformNormalByInverseViewMatrix( normal, viewMatrix );
	vec4 transmitted = getIBLVolumeRefraction(
		n, v, material.roughness, material.diffuseContribution, material.specularColorBlended, material.specularF90,
		pos, modelMatrix, viewMatrix, projectionMatrix, material.dispersion, material.ior, material.thickness,
		material.attenuationColor, material.attenuationDistance );
	material.transmissionAlpha = mix( material.transmissionAlpha, transmitted.a, material.transmission );
	totalDiffuse = mix( totalDiffuse, transmitted.rgb, material.transmission );
#endif`,transmission_pars_fragment:`#ifdef USE_TRANSMISSION
	uniform float transmission;
	uniform float thickness;
	uniform float attenuationDistance;
	uniform vec3 attenuationColor;
	#ifdef USE_TRANSMISSIONMAP
		uniform sampler2D transmissionMap;
	#endif
	#ifdef USE_THICKNESSMAP
		uniform sampler2D thicknessMap;
	#endif
	uniform vec2 transmissionSamplerSize;
	uniform sampler2D transmissionSamplerMap;
	uniform mat4 modelMatrix;
	uniform mat4 projectionMatrix;
	varying vec3 vWorldPosition;
	float w0( float a ) {
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - a + 3.0 ) - 3.0 ) + 1.0 );
	}
	float w1( float a ) {
		return ( 1.0 / 6.0 ) * ( a *  a * ( 3.0 * a - 6.0 ) + 4.0 );
	}
	float w2( float a ){
		return ( 1.0 / 6.0 ) * ( a * ( a * ( - 3.0 * a + 3.0 ) + 3.0 ) + 1.0 );
	}
	float w3( float a ) {
		return ( 1.0 / 6.0 ) * ( a * a * a );
	}
	float g0( float a ) {
		return w0( a ) + w1( a );
	}
	float g1( float a ) {
		return w2( a ) + w3( a );
	}
	float h0( float a ) {
		return - 1.0 + w1( a ) / ( w0( a ) + w1( a ) );
	}
	float h1( float a ) {
		return 1.0 + w3( a ) / ( w2( a ) + w3( a ) );
	}
	vec4 bicubic( sampler2D tex, vec2 uv, vec4 texelSize, float lod ) {
		uv = uv * texelSize.zw + 0.5;
		vec2 iuv = floor( uv );
		vec2 fuv = fract( uv );
		float g0x = g0( fuv.x );
		float g1x = g1( fuv.x );
		float h0x = h0( fuv.x );
		float h1x = h1( fuv.x );
		float h0y = h0( fuv.y );
		float h1y = h1( fuv.y );
		vec2 p0 = ( vec2( iuv.x + h0x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p1 = ( vec2( iuv.x + h1x, iuv.y + h0y ) - 0.5 ) * texelSize.xy;
		vec2 p2 = ( vec2( iuv.x + h0x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		vec2 p3 = ( vec2( iuv.x + h1x, iuv.y + h1y ) - 0.5 ) * texelSize.xy;
		return g0( fuv.y ) * ( g0x * textureLod( tex, p0, lod ) + g1x * textureLod( tex, p1, lod ) ) +
			g1( fuv.y ) * ( g0x * textureLod( tex, p2, lod ) + g1x * textureLod( tex, p3, lod ) );
	}
	vec4 textureBicubic( sampler2D sampler, vec2 uv, float lod ) {
		vec2 fLodSize = vec2( textureSize( sampler, int( lod ) ) );
		vec2 cLodSize = vec2( textureSize( sampler, int( lod + 1.0 ) ) );
		vec2 fLodSizeInv = 1.0 / fLodSize;
		vec2 cLodSizeInv = 1.0 / cLodSize;
		vec4 fSample = bicubic( sampler, uv, vec4( fLodSizeInv, fLodSize ), floor( lod ) );
		vec4 cSample = bicubic( sampler, uv, vec4( cLodSizeInv, cLodSize ), ceil( lod ) );
		return mix( fSample, cSample, fract( lod ) );
	}
	vec3 getVolumeTransmissionRay( const in vec3 n, const in vec3 v, const in float thickness, const in float ior, const in mat4 modelMatrix ) {
		vec3 refractionVector = refract( - v, normalize( n ), 1.0 / ior );
		vec3 modelScale;
		modelScale.x = length( vec3( modelMatrix[ 0 ].xyz ) );
		modelScale.y = length( vec3( modelMatrix[ 1 ].xyz ) );
		modelScale.z = length( vec3( modelMatrix[ 2 ].xyz ) );
		return normalize( refractionVector ) * thickness * modelScale;
	}
	float applyIorToRoughness( const in float roughness, const in float ior ) {
		return roughness * clamp( ior * 2.0 - 2.0, 0.0, 1.0 );
	}
	vec4 getTransmissionSample( const in vec2 fragCoord, const in float roughness, const in float ior ) {
		float lod = log2( transmissionSamplerSize.x ) * applyIorToRoughness( roughness, ior );
		return textureBicubic( transmissionSamplerMap, fragCoord.xy, lod );
	}
	vec3 volumeAttenuation( const in float transmissionDistance, const in vec3 attenuationColor, const in float attenuationDistance ) {
		if ( isinf( attenuationDistance ) ) {
			return vec3( 1.0 );
		} else {
			vec3 attenuationCoefficient = -log( attenuationColor ) / attenuationDistance;
			vec3 transmittance = exp( - attenuationCoefficient * transmissionDistance );			return transmittance;
		}
	}
	vec4 getIBLVolumeRefraction( const in vec3 n, const in vec3 v, const in float roughness, const in vec3 diffuseColor,
		const in vec3 specularColor, const in float specularF90, const in vec3 position, const in mat4 modelMatrix,
		const in mat4 viewMatrix, const in mat4 projMatrix, const in float dispersion, const in float ior, const in float thickness,
		const in vec3 attenuationColor, const in float attenuationDistance ) {
		vec4 transmittedLight;
		vec3 transmittance;
		#ifdef USE_DISPERSION
			float halfSpread = ( ior - 1.0 ) * 0.025 * dispersion;
			vec3 iors = vec3( ior - halfSpread, ior, ior + halfSpread );
			for ( int i = 0; i < 3; i ++ ) {
				vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, iors[ i ], modelMatrix );
				vec3 refractedRayExit = position + transmissionRay;
				vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
				vec2 refractionCoords = ndcPos.xy / ndcPos.w;
				refractionCoords += 1.0;
				refractionCoords /= 2.0;
				vec4 transmissionSample = getTransmissionSample( refractionCoords, roughness, iors[ i ] );
				transmittedLight[ i ] = transmissionSample[ i ];
				transmittedLight.a += transmissionSample.a;
				transmittance[ i ] = diffuseColor[ i ] * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance )[ i ];
			}
			transmittedLight.a /= 3.0;
		#else
			vec3 transmissionRay = getVolumeTransmissionRay( n, v, thickness, ior, modelMatrix );
			vec3 refractedRayExit = position + transmissionRay;
			vec4 ndcPos = projMatrix * viewMatrix * vec4( refractedRayExit, 1.0 );
			vec2 refractionCoords = ndcPos.xy / ndcPos.w;
			refractionCoords += 1.0;
			refractionCoords /= 2.0;
			transmittedLight = getTransmissionSample( refractionCoords, roughness, ior );
			transmittance = diffuseColor * volumeAttenuation( length( transmissionRay ), attenuationColor, attenuationDistance );
		#endif
		vec3 attenuatedColor = transmittance * transmittedLight.rgb;
		vec3 F = EnvironmentBRDF( n, v, specularColor, specularF90, roughness );
		float transmittanceFactor = ( transmittance.r + transmittance.g + transmittance.b ) / 3.0;
		return vec4( ( 1.0 - F ) * attenuatedColor, 1.0 - ( 1.0 - transmittedLight.a ) * transmittanceFactor );
	}
#endif`,uv_pars_fragment:`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_SPECULARMAP
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,uv_pars_vertex:`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	varying vec2 vUv;
#endif
#ifdef USE_MAP
	uniform mat3 mapTransform;
	varying vec2 vMapUv;
#endif
#ifdef USE_ALPHAMAP
	uniform mat3 alphaMapTransform;
	varying vec2 vAlphaMapUv;
#endif
#ifdef USE_LIGHTMAP
	uniform mat3 lightMapTransform;
	varying vec2 vLightMapUv;
#endif
#ifdef USE_AOMAP
	uniform mat3 aoMapTransform;
	varying vec2 vAoMapUv;
#endif
#ifdef USE_BUMPMAP
	uniform mat3 bumpMapTransform;
	varying vec2 vBumpMapUv;
#endif
#ifdef USE_NORMALMAP
	uniform mat3 normalMapTransform;
	varying vec2 vNormalMapUv;
#endif
#ifdef USE_DISPLACEMENTMAP
	uniform mat3 displacementMapTransform;
	varying vec2 vDisplacementMapUv;
#endif
#ifdef USE_EMISSIVEMAP
	uniform mat3 emissiveMapTransform;
	varying vec2 vEmissiveMapUv;
#endif
#ifdef USE_METALNESSMAP
	uniform mat3 metalnessMapTransform;
	varying vec2 vMetalnessMapUv;
#endif
#ifdef USE_ROUGHNESSMAP
	uniform mat3 roughnessMapTransform;
	varying vec2 vRoughnessMapUv;
#endif
#ifdef USE_ANISOTROPYMAP
	uniform mat3 anisotropyMapTransform;
	varying vec2 vAnisotropyMapUv;
#endif
#ifdef USE_CLEARCOATMAP
	uniform mat3 clearcoatMapTransform;
	varying vec2 vClearcoatMapUv;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	uniform mat3 clearcoatNormalMapTransform;
	varying vec2 vClearcoatNormalMapUv;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	uniform mat3 clearcoatRoughnessMapTransform;
	varying vec2 vClearcoatRoughnessMapUv;
#endif
#ifdef USE_SHEEN_COLORMAP
	uniform mat3 sheenColorMapTransform;
	varying vec2 vSheenColorMapUv;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	uniform mat3 sheenRoughnessMapTransform;
	varying vec2 vSheenRoughnessMapUv;
#endif
#ifdef USE_IRIDESCENCEMAP
	uniform mat3 iridescenceMapTransform;
	varying vec2 vIridescenceMapUv;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	uniform mat3 iridescenceThicknessMapTransform;
	varying vec2 vIridescenceThicknessMapUv;
#endif
#ifdef USE_SPECULARMAP
	uniform mat3 specularMapTransform;
	varying vec2 vSpecularMapUv;
#endif
#ifdef USE_SPECULAR_COLORMAP
	uniform mat3 specularColorMapTransform;
	varying vec2 vSpecularColorMapUv;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	uniform mat3 specularIntensityMapTransform;
	varying vec2 vSpecularIntensityMapUv;
#endif
#ifdef USE_TRANSMISSIONMAP
	uniform mat3 transmissionMapTransform;
	varying vec2 vTransmissionMapUv;
#endif
#ifdef USE_THICKNESSMAP
	uniform mat3 thicknessMapTransform;
	varying vec2 vThicknessMapUv;
#endif`,uv_vertex:`#if defined( USE_UV ) || defined( USE_ANISOTROPY )
	vUv = vec3( uv, 1 ).xy;
#endif
#ifdef USE_MAP
	vMapUv = ( mapTransform * vec3( MAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ALPHAMAP
	vAlphaMapUv = ( alphaMapTransform * vec3( ALPHAMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_LIGHTMAP
	vLightMapUv = ( lightMapTransform * vec3( LIGHTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_AOMAP
	vAoMapUv = ( aoMapTransform * vec3( AOMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_BUMPMAP
	vBumpMapUv = ( bumpMapTransform * vec3( BUMPMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_NORMALMAP
	vNormalMapUv = ( normalMapTransform * vec3( NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_DISPLACEMENTMAP
	vDisplacementMapUv = ( displacementMapTransform * vec3( DISPLACEMENTMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_EMISSIVEMAP
	vEmissiveMapUv = ( emissiveMapTransform * vec3( EMISSIVEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_METALNESSMAP
	vMetalnessMapUv = ( metalnessMapTransform * vec3( METALNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ROUGHNESSMAP
	vRoughnessMapUv = ( roughnessMapTransform * vec3( ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_ANISOTROPYMAP
	vAnisotropyMapUv = ( anisotropyMapTransform * vec3( ANISOTROPYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOATMAP
	vClearcoatMapUv = ( clearcoatMapTransform * vec3( CLEARCOATMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_NORMALMAP
	vClearcoatNormalMapUv = ( clearcoatNormalMapTransform * vec3( CLEARCOAT_NORMALMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_CLEARCOAT_ROUGHNESSMAP
	vClearcoatRoughnessMapUv = ( clearcoatRoughnessMapTransform * vec3( CLEARCOAT_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCEMAP
	vIridescenceMapUv = ( iridescenceMapTransform * vec3( IRIDESCENCEMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_IRIDESCENCE_THICKNESSMAP
	vIridescenceThicknessMapUv = ( iridescenceThicknessMapTransform * vec3( IRIDESCENCE_THICKNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_COLORMAP
	vSheenColorMapUv = ( sheenColorMapTransform * vec3( SHEEN_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SHEEN_ROUGHNESSMAP
	vSheenRoughnessMapUv = ( sheenRoughnessMapTransform * vec3( SHEEN_ROUGHNESSMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULARMAP
	vSpecularMapUv = ( specularMapTransform * vec3( SPECULARMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_COLORMAP
	vSpecularColorMapUv = ( specularColorMapTransform * vec3( SPECULAR_COLORMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_SPECULAR_INTENSITYMAP
	vSpecularIntensityMapUv = ( specularIntensityMapTransform * vec3( SPECULAR_INTENSITYMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_TRANSMISSIONMAP
	vTransmissionMapUv = ( transmissionMapTransform * vec3( TRANSMISSIONMAP_UV, 1 ) ).xy;
#endif
#ifdef USE_THICKNESSMAP
	vThicknessMapUv = ( thicknessMapTransform * vec3( THICKNESSMAP_UV, 1 ) ).xy;
#endif`,worldpos_vertex:`#if defined( USE_ENVMAP ) || defined( DISTANCE ) || defined ( USE_SHADOWMAP ) || defined ( USE_TRANSMISSION ) || NUM_SPOT_LIGHT_COORDS > 0
	vec4 worldPosition = vec4( transformed, 1.0 );
	#ifdef USE_BATCHING
		worldPosition = batchingMatrix * worldPosition;
	#endif
	#ifdef USE_INSTANCING
		worldPosition = instanceMatrix * worldPosition;
	#endif
	worldPosition = modelMatrix * worldPosition;
#endif`,background_vert:`varying vec2 vUv;
uniform mat3 uvTransform;
void main() {
	vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	gl_Position = vec4( position.xy, 1.0, 1.0 );
}`,background_frag:`uniform sampler2D t2D;
uniform float backgroundIntensity;
varying vec2 vUv;
void main() {
	vec4 texColor = texture2D( t2D, vUv );
	#ifdef DECODE_VIDEO_TEXTURE
		texColor = vec4( mix( pow( texColor.rgb * 0.9478672986 + vec3( 0.0521327014 ), vec3( 2.4 ) ), texColor.rgb * 0.0773993808, vec3( lessThanEqual( texColor.rgb, vec3( 0.04045 ) ) ) ), texColor.w );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,backgroundCube_vert:`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,backgroundCube_frag:`#ifdef ENVMAP_TYPE_CUBE
	uniform samplerCube envMap;
#elif defined( ENVMAP_TYPE_CUBE_UV )
	uniform sampler2D envMap;
#endif
uniform float backgroundBlurriness;
uniform float backgroundIntensity;
uniform mat3 backgroundRotation;
varying vec3 vWorldDirection;
#include <cube_uv_reflection_fragment>
void main() {
	#ifdef ENVMAP_TYPE_CUBE
		vec4 texColor = textureCube( envMap, backgroundRotation * vWorldDirection );
	#elif defined( ENVMAP_TYPE_CUBE_UV )
		vec4 texColor = textureCubeUV( envMap, backgroundRotation * vWorldDirection, backgroundBlurriness );
	#else
		vec4 texColor = vec4( 0.0, 0.0, 0.0, 1.0 );
	#endif
	texColor.rgb *= backgroundIntensity;
	gl_FragColor = texColor;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,cube_vert:`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
	gl_Position.z = gl_Position.w;
}`,cube_frag:`uniform samplerCube tCube;
uniform float tFlip;
uniform float opacity;
varying vec3 vWorldDirection;
void main() {
	vec4 texColor = textureCube( tCube, vec3( tFlip * vWorldDirection.x, vWorldDirection.yz ) );
	gl_FragColor = texColor;
	gl_FragColor.a *= opacity;
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,depth_vert:`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
varying vec2 vHighPrecisionZW;
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vHighPrecisionZW = gl_Position.zw;
}`,depth_frag:`#if DEPTH_PACKING == 3200
	uniform float opacity;
#endif
#include <common>
#include <packing>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
varying vec2 vHighPrecisionZW;
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#if DEPTH_PACKING == 3200
		diffuseColor.a = opacity;
	#endif
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <logdepthbuf_fragment>
	#ifdef USE_REVERSED_DEPTH_BUFFER
		float fragCoordZ = vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ];
	#else
		float fragCoordZ = 0.5 * vHighPrecisionZW[ 0 ] / vHighPrecisionZW[ 1 ] + 0.5;
	#endif
	#if DEPTH_PACKING == 3200
		gl_FragColor = vec4( vec3( 1.0 - fragCoordZ ), opacity );
	#elif DEPTH_PACKING == 3201
		gl_FragColor = packDepthToRGBA( fragCoordZ );
	#elif DEPTH_PACKING == 3202
		gl_FragColor = vec4( packDepthToRGB( fragCoordZ ), 1.0 );
	#elif DEPTH_PACKING == 3203
		gl_FragColor = vec4( packDepthToRG( fragCoordZ ), 0.0, 1.0 );
	#endif
}`,distance_vert:`#define DISTANCE
varying vec3 vWorldPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <skinbase_vertex>
	#include <morphinstance_vertex>
	#ifdef USE_DISPLACEMENTMAP
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <worldpos_vertex>
	#include <clipping_planes_vertex>
	vWorldPosition = worldPosition.xyz;
}`,distance_frag:`#define DISTANCE
uniform vec3 referencePosition;
uniform float nearDistance;
uniform float farDistance;
varying vec3 vWorldPosition;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 1.0 );
	#include <clipping_planes_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	float dist = length( vWorldPosition - referencePosition );
	dist = ( dist - nearDistance ) / ( farDistance - nearDistance );
	dist = saturate( dist );
	gl_FragColor = vec4( dist, 0.0, 0.0, 1.0 );
}`,equirect_vert:`varying vec3 vWorldDirection;
#include <common>
void main() {
	vWorldDirection = transformDirection( position, modelMatrix );
	#include <begin_vertex>
	#include <project_vertex>
}`,equirect_frag:`uniform sampler2D tEquirect;
varying vec3 vWorldDirection;
#include <common>
void main() {
	vec3 direction = normalize( vWorldDirection );
	vec2 sampleUV = equirectUv( direction );
	gl_FragColor = texture2D( tEquirect, sampleUV );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
}`,linedashed_vert:`uniform float scale;
attribute float lineDistance;
varying float vLineDistance;
#include <common>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	vLineDistance = scale * lineDistance;
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,linedashed_frag:`uniform vec3 diffuse;
uniform float opacity;
uniform float dashSize;
uniform float totalSize;
varying float vLineDistance;
#include <common>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	if ( mod( vLineDistance, totalSize ) > dashSize ) {
		discard;
	}
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,meshbasic_vert:`#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#if defined ( USE_ENVMAP ) || defined ( USE_SKINNING )
		#include <beginnormal_vertex>
		#include <morphnormal_vertex>
		#include <skinbase_vertex>
		#include <skinnormal_vertex>
		#include <defaultnormal_vertex>
	#endif
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <fog_vertex>
}`,meshbasic_frag:`uniform vec3 diffuse;
uniform float opacity;
#ifndef FLAT_SHADED
	varying vec3 vNormal;
#endif
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <fog_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	#ifdef USE_LIGHTMAP
		vec4 lightMapTexel = texture2D( lightMap, vLightMapUv );
		reflectedLight.indirectDiffuse += lightMapTexel.rgb * lightMapIntensity * RECIPROCAL_PI;
	#else
		reflectedLight.indirectDiffuse += vec3( 1.0 );
	#endif
	#include <aomap_fragment>
	reflectedLight.indirectDiffuse *= diffuseColor.rgb;
	vec3 outgoingLight = reflectedLight.indirectDiffuse;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,meshlambert_vert:`#define LAMBERT
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,meshlambert_frag:`#define LAMBERT
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_lambert_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_lambert_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,meshmatcap_vert:`#define MATCAP
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <color_pars_vertex>
#include <displacementmap_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
	vViewPosition = - mvPosition.xyz;
}`,meshmatcap_frag:`#define MATCAP
uniform vec3 diffuse;
uniform float opacity;
uniform sampler2D matcap;
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	vec3 viewDir = normalize( vViewPosition );
	vec3 x = normalize( vec3( viewDir.z, 0.0, - viewDir.x ) );
	vec3 y = cross( viewDir, x );
	vec2 uv = vec2( dot( x, normal ), dot( y, normal ) ) * 0.495 + 0.5;
	#ifdef USE_MATCAP
		vec4 matcapColor = texture2D( matcap, uv );
	#else
		vec4 matcapColor = vec4( vec3( mix( 0.2, 0.8, uv.y ) ), 1.0 );
	#endif
	vec3 outgoingLight = diffuseColor.rgb * matcapColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,meshnormal_vert:`#define NORMAL
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	vViewPosition = - mvPosition.xyz;
#endif
}`,meshnormal_frag:`#define NORMAL
uniform float opacity;
#if defined( FLAT_SHADED ) || defined( USE_BUMPMAP ) || defined( USE_NORMALMAP_TANGENTSPACE )
	varying vec3 vViewPosition;
#endif
#include <uv_pars_fragment>
#include <normal_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( 0.0, 0.0, 0.0, opacity );
	#include <clipping_planes_fragment>
	#include <logdepthbuf_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	gl_FragColor = vec4( normalize( normal ) * 0.5 + 0.5, diffuseColor.a );
	#ifdef OPAQUE
		gl_FragColor.a = 1.0;
	#endif
}`,meshphong_vert:`#define PHONG
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <envmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <envmap_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,meshphong_frag:`#define PHONG
uniform vec3 diffuse;
uniform vec3 emissive;
uniform vec3 specular;
uniform float shininess;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_phong_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <specularmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <specularmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_phong_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + reflectedLight.directSpecular + reflectedLight.indirectSpecular + totalEmissiveRadiance;
	#include <envmap_fragment>
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,meshphysical_vert:`#define STANDARD
varying vec3 vViewPosition;
#ifdef USE_TRANSMISSION
	varying vec3 vWorldPosition;
#endif
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
#ifdef USE_TRANSMISSION
	vWorldPosition = worldPosition.xyz;
#endif
}`,meshphysical_frag:`#define STANDARD
#ifdef PHYSICAL
	#define IOR
	#define USE_SPECULAR
#endif
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float roughness;
uniform float metalness;
uniform float opacity;
#ifdef IOR
	uniform float ior;
#endif
#ifdef USE_SPECULAR
	uniform float specularIntensity;
	uniform vec3 specularColor;
	#ifdef USE_SPECULAR_COLORMAP
		uniform sampler2D specularColorMap;
	#endif
	#ifdef USE_SPECULAR_INTENSITYMAP
		uniform sampler2D specularIntensityMap;
	#endif
#endif
#ifdef USE_CLEARCOAT
	uniform float clearcoat;
	uniform float clearcoatRoughness;
#endif
#ifdef USE_DISPERSION
	uniform float dispersion;
#endif
#ifdef USE_RETROREFLECTION
	uniform float retroreflectivity;
#endif
#ifdef USE_IRIDESCENCE
	uniform float iridescence;
	uniform float iridescenceIOR;
	uniform float iridescenceThicknessMinimum;
	uniform float iridescenceThicknessMaximum;
#endif
#ifdef USE_SHEEN
	uniform vec3 sheenColor;
	uniform float sheenRoughness;
	#ifdef USE_SHEEN_COLORMAP
		uniform sampler2D sheenColorMap;
	#endif
	#ifdef USE_SHEEN_ROUGHNESSMAP
		uniform sampler2D sheenRoughnessMap;
	#endif
#endif
#ifdef USE_ANISOTROPY
	uniform vec2 anisotropyVector;
	#ifdef USE_ANISOTROPYMAP
		uniform sampler2D anisotropyMap;
	#endif
#endif
varying vec3 vViewPosition;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <iridescence_fragment>
#include <cube_uv_reflection_fragment>
#include <envmap_common_pars_fragment>
#include <envmap_physical_pars_fragment>
#include <fog_pars_fragment>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_physical_pars_fragment>
#include <transmission_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <clearcoat_pars_fragment>
#include <iridescence_pars_fragment>
#include <roughnessmap_pars_fragment>
#include <metalnessmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <roughnessmap_fragment>
	#include <metalnessmap_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <clearcoat_normal_fragment_begin>
	#include <clearcoat_normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_physical_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 totalDiffuse = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse;
	vec3 totalSpecular = reflectedLight.directSpecular + reflectedLight.indirectSpecular;
	#include <transmission_fragment>
	vec3 outgoingLight = totalDiffuse + totalSpecular + totalEmissiveRadiance;
	#ifdef USE_SHEEN
 
		outgoingLight = outgoingLight + sheenSpecularDirect + sheenSpecularIndirect;
 
 	#endif
	#ifdef USE_CLEARCOAT
		float dotNVcc = saturate( dot( geometryClearcoatNormal, geometryViewDir ) );
		vec3 Fcc = F_Schlick( material.clearcoatF0, material.clearcoatF90, dotNVcc );
		outgoingLight = outgoingLight * ( 1.0 - material.clearcoat * Fcc ) + ( clearcoatSpecularDirect + clearcoatSpecularIndirect ) * material.clearcoat;
	#endif
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,meshtoon_vert:`#define TOON
varying vec3 vViewPosition;
#include <common>
#include <batching_pars_vertex>
#include <uv_pars_vertex>
#include <displacementmap_pars_vertex>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <normal_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <shadowmap_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <normal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <displacementmap_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	vViewPosition = - mvPosition.xyz;
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,meshtoon_frag:`#define TOON
uniform vec3 diffuse;
uniform vec3 emissive;
uniform float opacity;
#include <common>
#include <dithering_pars_fragment>
#include <color_pars_fragment>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <aomap_pars_fragment>
#include <lightmap_pars_fragment>
#include <emissivemap_pars_fragment>
#include <gradientmap_pars_fragment>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <normal_pars_fragment>
#include <lights_toon_pars_fragment>
#include <shadowmap_pars_fragment>
#include <bumpmap_pars_fragment>
#include <normalmap_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	ReflectedLight reflectedLight = ReflectedLight( vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ), vec3( 0.0 ) );
	vec3 totalEmissiveRadiance = emissive;
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <color_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	#include <normal_fragment_begin>
	#include <normal_fragment_maps>
	#include <emissivemap_fragment>
	#include <lights_toon_fragment>
	#include <lights_fragment_begin>
	#include <lights_fragment_maps>
	#include <lights_fragment_end>
	#include <aomap_fragment>
	vec3 outgoingLight = reflectedLight.directDiffuse + reflectedLight.indirectDiffuse + totalEmissiveRadiance;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
	#include <dithering_fragment>
}`,points_vert:`uniform float size;
uniform float scale;
#include <common>
#include <color_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
#ifdef USE_POINTS_UV
	varying vec2 vUv;
	uniform mat3 uvTransform;
#endif
void main() {
	#ifdef USE_POINTS_UV
		vUv = ( uvTransform * vec3( uv, 1 ) ).xy;
	#endif
	#include <color_vertex>
	#include <morphinstance_vertex>
	#include <morphcolor_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <project_vertex>
	gl_PointSize = size;
	#ifdef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) gl_PointSize *= ( scale / - mvPosition.z );
	#endif
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <worldpos_vertex>
	#include <fog_vertex>
}`,points_frag:`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <color_pars_fragment>
#include <map_particle_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_particle_fragment>
	#include <color_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,shadow_vert:`#include <common>
#include <batching_pars_vertex>
#include <fog_pars_vertex>
#include <morphtarget_pars_vertex>
#include <skinning_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <shadowmap_pars_vertex>
void main() {
	#include <batching_vertex>
	#include <beginnormal_vertex>
	#include <morphinstance_vertex>
	#include <morphnormal_vertex>
	#include <skinbase_vertex>
	#include <skinnormal_vertex>
	#include <defaultnormal_vertex>
	#include <begin_vertex>
	#include <morphtarget_vertex>
	#include <skinning_vertex>
	#include <project_vertex>
	#include <logdepthbuf_vertex>
	#include <worldpos_vertex>
	#include <shadowmap_vertex>
	#include <fog_vertex>
}`,shadow_frag:`uniform vec3 color;
uniform float opacity;
#include <common>
#include <fog_pars_fragment>
#include <bsdfs>
#include <lights_pars_begin>
#include <logdepthbuf_pars_fragment>
#include <shadowmap_pars_fragment>
#include <shadowmask_pars_fragment>
void main() {
	#include <logdepthbuf_fragment>
	gl_FragColor = vec4( color, opacity * ( 1.0 - getShadowMask() ) );
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
	#include <premultiplied_alpha_fragment>
}`,sprite_vert:`uniform float rotation;
uniform vec2 center;
#include <common>
#include <uv_pars_vertex>
#include <fog_pars_vertex>
#include <logdepthbuf_pars_vertex>
#include <clipping_planes_pars_vertex>
void main() {
	#include <uv_vertex>
	vec4 mvPosition = modelViewMatrix[ 3 ];
	vec2 scale = vec2( length( modelMatrix[ 0 ].xyz ), length( modelMatrix[ 1 ].xyz ) );
	#ifndef USE_SIZEATTENUATION
		bool isPerspective = isPerspectiveMatrix( projectionMatrix );
		if ( isPerspective ) scale *= - mvPosition.z;
	#endif
	vec2 alignedPosition = ( position.xy - ( center - vec2( 0.5 ) ) ) * scale;
	vec2 rotatedPosition;
	rotatedPosition.x = cos( rotation ) * alignedPosition.x - sin( rotation ) * alignedPosition.y;
	rotatedPosition.y = sin( rotation ) * alignedPosition.x + cos( rotation ) * alignedPosition.y;
	mvPosition.xy += rotatedPosition;
	gl_Position = projectionMatrix * mvPosition;
	#include <logdepthbuf_vertex>
	#include <clipping_planes_vertex>
	#include <fog_vertex>
}`,sprite_frag:`uniform vec3 diffuse;
uniform float opacity;
#include <common>
#include <uv_pars_fragment>
#include <map_pars_fragment>
#include <alphamap_pars_fragment>
#include <alphatest_pars_fragment>
#include <alphahash_pars_fragment>
#include <fog_pars_fragment>
#include <logdepthbuf_pars_fragment>
#include <clipping_planes_pars_fragment>
void main() {
	vec4 diffuseColor = vec4( diffuse, opacity );
	#include <clipping_planes_fragment>
	vec3 outgoingLight = vec3( 0.0 );
	#include <logdepthbuf_fragment>
	#include <map_fragment>
	#include <alphamap_fragment>
	#include <alphatest_fragment>
	#include <alphahash_fragment>
	outgoingLight = diffuseColor.rgb;
	#include <opaque_fragment>
	#include <tonemapping_fragment>
	#include <colorspace_fragment>
	#include <fog_fragment>
}`},$={common:{diffuse:{value:new mc(16777215)},opacity:{value:1},map:{value:null},mapTransform:{value:new Z},alphaMap:{value:null},alphaMapTransform:{value:new Z},alphaTest:{value:0}},specularmap:{specularMap:{value:null},specularMapTransform:{value:new Z}},envmap:{envMap:{value:null},envMapRotation:{value:new Z},reflectivity:{value:1},ior:{value:1.5},refractionRatio:{value:.98},dfgLUT:{value:null}},aomap:{aoMap:{value:null},aoMapIntensity:{value:1},aoMapTransform:{value:new Z}},lightmap:{lightMap:{value:null},lightMapIntensity:{value:1},lightMapTransform:{value:new Z}},bumpmap:{bumpMap:{value:null},bumpMapTransform:{value:new Z},bumpScale:{value:1}},normalmap:{normalMap:{value:null},normalMapTransform:{value:new Z},normalScale:{value:new Y(1,1)}},displacementmap:{displacementMap:{value:null},displacementMapTransform:{value:new Z},displacementScale:{value:1},displacementBias:{value:0}},emissivemap:{emissiveMap:{value:null},emissiveMapTransform:{value:new Z}},metalnessmap:{metalnessMap:{value:null},metalnessMapTransform:{value:new Z}},roughnessmap:{roughnessMap:{value:null},roughnessMapTransform:{value:new Z}},gradientmap:{gradientMap:{value:null}},fog:{fogDensity:{value:25e-5},fogNear:{value:1},fogFar:{value:2e3},fogColor:{value:new mc(16777215)}},lights:{ambientLightColor:{value:[]},lightProbe:{value:[]},sunLights:{value:[],properties:{direction:{},color:{}}},sunLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},sunShadowMatrix:{value:[]},sunShadowCascade:{value:[]},directionalLights:{value:[],properties:{direction:{},color:{}}},directionalLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},directionalShadowMatrix:{value:[]},spotLights:{value:[],properties:{color:{},position:{},direction:{},distance:{},coneCos:{},penumbraCos:{},decay:{}}},spotLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{}}},spotLightMap:{value:[]},spotLightMatrix:{value:[]},pointLights:{value:[],properties:{color:{},position:{},decay:{},distance:{}}},pointLightShadows:{value:[],properties:{shadowIntensity:1,shadowBias:{},shadowNormalBias:{},shadowRadius:{},shadowMapSize:{},shadowCameraNear:{},shadowCameraFar:{}}},pointShadowMatrix:{value:[]},hemisphereLights:{value:[],properties:{direction:{},skyColor:{},groundColor:{}}},rectAreaLights:{value:[],properties:{color:{},position:{},width:{},height:{}}},ltc_1:{value:null},ltc_2:{value:null},probesSH:{value:null},probesMin:{value:new X},probesMax:{value:new X},probesResolution:{value:new X}},points:{diffuse:{value:new mc(16777215)},opacity:{value:1},size:{value:1},scale:{value:1},map:{value:null},alphaMap:{value:null},alphaMapTransform:{value:new Z},alphaTest:{value:0},uvTransform:{value:new Z}},sprite:{diffuse:{value:new mc(16777215)},opacity:{value:1},center:{value:new Y(.5,.5)},rotation:{value:0},map:{value:null},mapTransform:{value:new Z},alphaMap:{value:null},alphaMapTransform:{value:new Z},alphaTest:{value:0}}},Of={basic:{uniforms:Xu([$.common,$.specularmap,$.envmap,$.aomap,$.lightmap,$.fog]),vertexShader:Df.meshbasic_vert,fragmentShader:Df.meshbasic_frag},lambert:{uniforms:Xu([$.common,$.specularmap,$.envmap,$.aomap,$.lightmap,$.emissivemap,$.bumpmap,$.normalmap,$.displacementmap,$.fog,$.lights,{emissive:{value:new mc(0)},envMapIntensity:{value:1}}]),vertexShader:Df.meshlambert_vert,fragmentShader:Df.meshlambert_frag},phong:{uniforms:Xu([$.common,$.specularmap,$.envmap,$.aomap,$.lightmap,$.emissivemap,$.bumpmap,$.normalmap,$.displacementmap,$.fog,$.lights,{emissive:{value:new mc(0)},specular:{value:new mc(1118481)},shininess:{value:30},envMapIntensity:{value:1}}]),vertexShader:Df.meshphong_vert,fragmentShader:Df.meshphong_frag},standard:{uniforms:Xu([$.common,$.envmap,$.aomap,$.lightmap,$.emissivemap,$.bumpmap,$.normalmap,$.displacementmap,$.roughnessmap,$.metalnessmap,$.fog,$.lights,{emissive:{value:new mc(0)},roughness:{value:1},metalness:{value:0},envMapIntensity:{value:1}}]),vertexShader:Df.meshphysical_vert,fragmentShader:Df.meshphysical_frag},toon:{uniforms:Xu([$.common,$.aomap,$.lightmap,$.emissivemap,$.bumpmap,$.normalmap,$.displacementmap,$.gradientmap,$.fog,$.lights,{emissive:{value:new mc(0)}}]),vertexShader:Df.meshtoon_vert,fragmentShader:Df.meshtoon_frag},matcap:{uniforms:Xu([$.common,$.bumpmap,$.normalmap,$.displacementmap,$.fog,{matcap:{value:null}}]),vertexShader:Df.meshmatcap_vert,fragmentShader:Df.meshmatcap_frag},points:{uniforms:Xu([$.points,$.fog]),vertexShader:Df.points_vert,fragmentShader:Df.points_frag},dashed:{uniforms:Xu([$.common,$.fog,{scale:{value:1},dashSize:{value:1},totalSize:{value:2}}]),vertexShader:Df.linedashed_vert,fragmentShader:Df.linedashed_frag},depth:{uniforms:Xu([$.common,$.displacementmap]),vertexShader:Df.depth_vert,fragmentShader:Df.depth_frag},normal:{uniforms:Xu([$.common,$.bumpmap,$.normalmap,$.displacementmap,{opacity:{value:1}}]),vertexShader:Df.meshnormal_vert,fragmentShader:Df.meshnormal_frag},sprite:{uniforms:Xu([$.sprite,$.fog]),vertexShader:Df.sprite_vert,fragmentShader:Df.sprite_frag},background:{uniforms:{uvTransform:{value:new Z},t2D:{value:null},backgroundIntensity:{value:1}},vertexShader:Df.background_vert,fragmentShader:Df.background_frag},backgroundCube:{uniforms:{envMap:{value:null},backgroundBlurriness:{value:0},backgroundIntensity:{value:1},backgroundRotation:{value:new Z}},vertexShader:Df.backgroundCube_vert,fragmentShader:Df.backgroundCube_frag},cube:{uniforms:{tCube:{value:null},tFlip:{value:-1},opacity:{value:1}},vertexShader:Df.cube_vert,fragmentShader:Df.cube_frag},equirect:{uniforms:{tEquirect:{value:null}},vertexShader:Df.equirect_vert,fragmentShader:Df.equirect_frag},distance:{uniforms:Xu([$.common,$.displacementmap,{referencePosition:{value:new X},nearDistance:{value:1},farDistance:{value:1e3}}]),vertexShader:Df.distance_vert,fragmentShader:Df.distance_frag},shadow:{uniforms:Xu([$.lights,$.fog,{color:{value:new mc(0)},opacity:{value:1}}]),vertexShader:Df.shadow_vert,fragmentShader:Df.shadow_frag}};Of.physical={uniforms:Xu([Of.standard.uniforms,{clearcoat:{value:0},clearcoatMap:{value:null},clearcoatMapTransform:{value:new Z},clearcoatNormalMap:{value:null},clearcoatNormalMapTransform:{value:new Z},clearcoatNormalScale:{value:new Y(1,1)},clearcoatRoughness:{value:0},clearcoatRoughnessMap:{value:null},clearcoatRoughnessMapTransform:{value:new Z},dispersion:{value:0},retroreflectivity:{value:0},iridescence:{value:0},iridescenceMap:{value:null},iridescenceMapTransform:{value:new Z},iridescenceIOR:{value:1.3},iridescenceThicknessMinimum:{value:100},iridescenceThicknessMaximum:{value:400},iridescenceThicknessMap:{value:null},iridescenceThicknessMapTransform:{value:new Z},sheen:{value:0},sheenColor:{value:new mc(0)},sheenColorMap:{value:null},sheenColorMapTransform:{value:new Z},sheenRoughness:{value:1},sheenRoughnessMap:{value:null},sheenRoughnessMapTransform:{value:new Z},transmission:{value:0},transmissionMap:{value:null},transmissionMapTransform:{value:new Z},transmissionSamplerSize:{value:new Y},transmissionSamplerMap:{value:null},thickness:{value:0},thicknessMap:{value:null},thicknessMapTransform:{value:new Z},attenuationDistance:{value:0},attenuationColor:{value:new mc(0)},specularColor:{value:new mc(1,1,1)},specularColorMap:{value:null},specularColorMapTransform:{value:new Z},specularIntensity:{value:1},specularIntensityMap:{value:null},specularIntensityMapTransform:{value:new Z},anisotropyVector:{value:new Y},anisotropyMap:{value:null},anisotropyMapTransform:{value:new Z}}]),vertexShader:Df.meshphysical_vert,fragmentShader:Df.meshphysical_frag};var kf={r:0,b:0,g:0},Af=new Ps,jf=new Z;jf.set(-1,0,0,0,1,0,0,0,1);function Mf(e,t,n,r,i,a){let o=new mc(0),s=i===!0?0:1,c,l,u=null,d=0,f=null;function p(e){let n=e.isScene===!0?e.background:null;if(n&&n.isTexture){let r=e.backgroundBlurriness>0;n=t.get(n,r)}return n}function m(t){let r=!1,i=p(t);i===null?g(o,s):i&&i.isColor&&(g(i,1),r=!0);let c=e.xr.getEnvironmentBlendMode();c===`additive`?n.buffers.color.setClear(0,0,0,1,a):c===`alpha-blend`&&n.buffers.color.setClear(0,0,0,0,a),(e.autoClear||r)&&(n.buffers.depth.setTest(!0),n.buffers.depth.setMask(!0),n.buffers.color.setMask(!0),e.clear(e.autoClearColor,e.autoClearDepth,e.autoClearStencil))}function h(t,n){let i=p(n);i&&(i.isCubeTexture||i.mapping===306)?(l===void 0&&(l=new Ll(new gu(1,1,1),new rd({name:`BackgroundCubeMaterial`,uniforms:Yu(Of.backgroundCube.uniforms),vertexShader:Of.backgroundCube.vertexShader,fragmentShader:Of.backgroundCube.fragmentShader,side:1,depthTest:!1,depthWrite:!1,fog:!1,allowOverride:!1})),l.geometry.deleteAttribute(`normal`),l.geometry.deleteAttribute(`uv`),l.onBeforeRender=function(e,t,n){this.matrixWorld.copyPosition(n.matrixWorld)},Object.defineProperty(l.material,"envMap",{get:function(){return this.uniforms.envMap.value}}),r.update(l)),l.material.uniforms.envMap.value=i,l.material.uniforms.backgroundBlurriness.value=n.backgroundBlurriness,l.material.uniforms.backgroundIntensity.value=n.backgroundIntensity,l.material.uniforms.backgroundRotation.value.setFromMatrix4(Af.makeRotationFromEuler(n.backgroundRotation)).transpose(),i.isCubeTexture&&i.isRenderTargetTexture===!1&&l.material.uniforms.backgroundRotation.value.premultiply(jf),l.material.toneMapped=vs.getTransfer(i.colorSpace)!==wo,(u!==i||d!==i.version||f!==e.toneMapping)&&(l.material.needsUpdate=!0,u=i,d=i.version,f=e.toneMapping),l.layers.enableAll(),t.unshift(l,l.geometry,l.material,0,0,null)):i&&i.isTexture&&(c===void 0&&(c=new Ll(new Wu(2,2),new rd({name:`BackgroundMaterial`,uniforms:Yu(Of.background.uniforms),vertexShader:Of.background.vertexShader,fragmentShader:Of.background.fragmentShader,side:0,depthTest:!1,depthWrite:!1,fog:!1,allowOverride:!1})),c.geometry.deleteAttribute(`normal`),Object.defineProperty(c.material,"map",{get:function(){return this.uniforms.t2D.value}}),r.update(c)),c.material.uniforms.t2D.value=i,c.material.uniforms.backgroundIntensity.value=n.backgroundIntensity,c.material.toneMapped=vs.getTransfer(i.colorSpace)!==wo,i.matrixAutoUpdate===!0&&i.updateMatrix(),c.material.uniforms.uvTransform.value.copy(i.matrix),(u!==i||d!==i.version||f!==e.toneMapping)&&(c.material.needsUpdate=!0,u=i,d=i.version,f=e.toneMapping),c.layers.enableAll(),t.unshift(c,c.geometry,c.material,0,0,null))}function g(t,r){t.getRGB(kf,$u(e)),n.buffers.color.setClear(kf.r,kf.g,kf.b,r,a)}function _(){l!==void 0&&(l.geometry.dispose(),l.material.dispose(),l=void 0),c!==void 0&&(c.geometry.dispose(),c.material.dispose(),c=void 0)}return{getClearColor:function(){return o},setClearColor:function(e,t=1){o.set(e),s=t,g(o,s)},getClearAlpha:function(){return s},setClearAlpha:function(e){s=e,g(o,s)},render:m,addToRenderList:h,dispose:_}}function Nf(e,t){let n=e.getParameter(e.MAX_VERTEX_ATTRIBS),r={},i=f(null),a=i,o=!1;function s(n,r,i,s,c){let u=!1,f=d(n,s,i,r);a!==f&&(a=f,l(a.object)),u=p(n,s,i,c),u&&m(n,s,i,c),c!==null&&t.update(c,e.ELEMENT_ARRAY_BUFFER),(u||o)&&(o=!1,b(n,r,i,s),c!==null&&e.bindBuffer(e.ELEMENT_ARRAY_BUFFER,t.get(c).buffer))}function c(){return e.createVertexArray()}function l(t){return e.bindVertexArray(t)}function u(t){return e.deleteVertexArray(t)}function d(e,t,n,i){let a=i.wireframe===!0,o=r[t.id];o===void 0&&(o={},r[t.id]=o);let s=e.isInstancedMesh===!0?e.id:0,l=o[s];l===void 0&&(l={},o[s]=l);let u=l[n.id];u===void 0&&(u={},l[n.id]=u);let d=u[a];return d===void 0&&(d=f(c()),u[a]=d),d}function f(e){let t=[],r=[],i=[];for(let e=0;e<n;e++)t[e]=0,r[e]=0,i[e]=0;return{geometry:null,program:null,wireframe:!1,newAttributes:t,enabledAttributes:r,attributeDivisors:i,object:e,attributes:{},index:null}}function p(e,t,n,r){let i=a.attributes,o=t.attributes,s=0,c=n.getAttributes();for(let t in c)if(c[t].location>=0){let n=i[t],r=o[t];if(r===void 0&&(t===`instanceMatrix`&&e.instanceMatrix&&(r=e.instanceMatrix),t===`instanceColor`&&e.instanceColor&&(r=e.instanceColor)),n===void 0||n.attribute!==r||r&&n.data!==r.data)return!0;s++}return a.attributesNum!==s||a.index!==r}function m(e,t,n,r){let i={},o=t.attributes,s=0,c=n.getAttributes();for(let t in c)if(c[t].location>=0){let n=o[t];n===void 0&&(t===`instanceMatrix`&&e.instanceMatrix&&(n=e.instanceMatrix),t===`instanceColor`&&e.instanceColor&&(n=e.instanceColor));let r={};r.attribute=n,n&&n.data&&(r.data=n.data),i[t]=r,s++}a.attributes=i,a.attributesNum=s,a.index=r}function h(){let e=a.newAttributes;for(let t=0,n=e.length;t<n;t++)e[t]=0}function g(e){_(e,0)}function _(t,n){let r=a.newAttributes,i=a.enabledAttributes,o=a.attributeDivisors;r[t]=1,i[t]===0&&(e.enableVertexAttribArray(t),i[t]=1),o[t]!==n&&(e.vertexAttribDivisor(t,n),o[t]=n)}function v(){let t=a.newAttributes,n=a.enabledAttributes;for(let r=0,i=n.length;r<i;r++)n[r]!==t[r]&&(e.disableVertexAttribArray(r),n[r]=0)}function y(t,n,r,i,a,o,s){s===!0?e.vertexAttribIPointer(t,n,r,a,o):e.vertexAttribPointer(t,n,r,i,a,o)}function b(n,r,i,a){h();let o=a.attributes,s=i.getAttributes(),c=r.defaultAttributeValues;for(let r in s){let i=s[r];if(i.location>=0){let s=o[r];if(s===void 0&&(r===`instanceMatrix`&&n.instanceMatrix&&(s=n.instanceMatrix),r===`instanceColor`&&n.instanceColor&&(s=n.instanceColor)),s!==void 0){let r=s.normalized,o=s.itemSize,c=t.get(s);if(c===void 0)continue;let l=c.buffer,u=c.type,d=c.bytesPerElement,f=u===e.INT||u===e.UNSIGNED_INT||s.gpuType===1013;if(s.isInterleavedBufferAttribute){let t=s.data,c=t.stride,p=s.offset;if(t.isInstancedInterleavedBuffer){for(let e=0;e<i.locationSize;e++)_(i.location+e,t.meshPerAttribute);n.isInstancedMesh!==!0&&a._maxInstanceCount===void 0&&(a._maxInstanceCount=t.meshPerAttribute*t.count)}else for(let e=0;e<i.locationSize;e++)g(i.location+e);e.bindBuffer(e.ARRAY_BUFFER,l);for(let e=0;e<i.locationSize;e++)y(i.location+e,o/i.locationSize,u,r,c*d,(p+o/i.locationSize*e)*d,f)}else{if(s.isInstancedBufferAttribute){for(let e=0;e<i.locationSize;e++)_(i.location+e,s.meshPerAttribute);n.isInstancedMesh!==!0&&a._maxInstanceCount===void 0&&(a._maxInstanceCount=s.meshPerAttribute*s.count)}else for(let e=0;e<i.locationSize;e++)g(i.location+e);e.bindBuffer(e.ARRAY_BUFFER,l);for(let e=0;e<i.locationSize;e++)y(i.location+e,o/i.locationSize,u,r,o*d,o/i.locationSize*e*d,f)}}else if(c!==void 0){let t=c[r];if(t!==void 0)switch(t.length){case 2:e.vertexAttrib2fv(i.location,t);break;case 3:e.vertexAttrib3fv(i.location,t);break;case 4:e.vertexAttrib4fv(i.location,t);break;default:e.vertexAttrib1fv(i.location,t)}}}}v()}function x(){T();for(let e in r){let t=r[e];for(let e in t){let n=t[e];for(let e in n){let t=n[e];for(let e in t)u(t[e].object),delete t[e];delete n[e]}}delete r[e]}}function S(e){if(r[e.id]===void 0)return;let t=r[e.id];for(let e in t){let n=t[e];for(let e in n){let t=n[e];for(let e in t)u(t[e].object),delete t[e];delete n[e]}}delete r[e.id]}function C(e){for(let t in r){let n=r[t];for(let t in n){let r=n[t];if(r[e.id]===void 0)continue;let i=r[e.id];for(let e in i)u(i[e].object),delete i[e];delete r[e.id]}}}function w(e){for(let t in r){let n=r[t],i=e.isInstancedMesh===!0?e.id:0,a=n[i];if(a!==void 0){for(let e in a){let t=a[e];for(let e in t)u(t[e].object),delete t[e];delete a[e]}delete n[i],Object.keys(n).length===0&&delete r[t]}}}function T(){E(),o=!0,a!==i&&(a=i,l(a.object))}function E(){i.geometry=null,i.program=null,i.wireframe=!1}return{setup:s,reset:T,resetDefaultState:E,dispose:x,releaseStatesOfGeometry:S,releaseStatesOfObject:w,releaseStatesOfProgram:C,initAttributes:h,enableAttribute:g,disableUnusedAttributes:v}}function Pf(e,t,n){let r;function i(e){r=e}function a(t,i){e.drawArrays(r,t,i),n.update(i,r,1)}function o(t,i,a){a!==0&&(e.drawArraysInstanced(r,t,i,a),n.update(i,r,a))}function s(e,i,a){if(a===0)return;t.get(`WEBGL_multi_draw`).multiDrawArraysWEBGL(r,e,0,i,0,a);let o=0;for(let e=0;e<a;e++)o+=i[e];n.update(o,r,1)}this.setMode=i,this.render=a,this.renderInstances=o,this.renderMultiDraw=s}function Ff(e,t,n,r){let i;function a(){if(i!==void 0)return i;if(t.has(`EXT_texture_filter_anisotropic`)===!0){let n=t.get(`EXT_texture_filter_anisotropic`);i=e.getParameter(n.MAX_TEXTURE_MAX_ANISOTROPY_EXT)}else i=0;return i}function o(t){return t===1023||r.convert(t)===e.getParameter(e.IMPLEMENTATION_COLOR_READ_FORMAT)}function s(n){let i=n===1016&&(t.has(`EXT_color_buffer_half_float`)||t.has(`EXT_color_buffer_float`));return!(n!==1009&&n!==1015&&!i&&r.convert(n)!==e.getParameter(e.IMPLEMENTATION_COLOR_READ_TYPE))}function c(t){if(t===`highp`){if(e.getShaderPrecisionFormat(e.VERTEX_SHADER,e.HIGH_FLOAT).precision>0&&e.getShaderPrecisionFormat(e.FRAGMENT_SHADER,e.HIGH_FLOAT).precision>0)return`highp`;t=`mediump`}return t===`mediump`&&e.getShaderPrecisionFormat(e.VERTEX_SHADER,e.MEDIUM_FLOAT).precision>0&&e.getShaderPrecisionFormat(e.FRAGMENT_SHADER,e.MEDIUM_FLOAT).precision>0?`mediump`:`lowp`}let l=n.precision===void 0?`highp`:n.precision,u=c(l);u!==l&&(K(`WebGLRenderer:`,l,`not supported, using`,u,`instead.`),l=u);let d=n.logarithmicDepthBuffer===!0,f=n.reversedDepthBuffer===!0&&t.has(`EXT_clip_control`);n.reversedDepthBuffer===!0&&f===!1&&K(`WebGLRenderer: Unable to use reversed depth buffer due to missing EXT_clip_control extension. Fallback to default depth buffer.`);let p=e.getParameter(e.MAX_TEXTURE_IMAGE_UNITS),m=e.getParameter(e.MAX_VERTEX_TEXTURE_IMAGE_UNITS),h=e.getParameter(e.MAX_TEXTURE_SIZE),g=e.getParameter(e.MAX_CUBE_MAP_TEXTURE_SIZE),_=e.getParameter(e.MAX_VERTEX_ATTRIBS),v=e.getParameter(e.MAX_VERTEX_UNIFORM_VECTORS),y=e.getParameter(e.MAX_VARYING_VECTORS),b=e.getParameter(e.MAX_FRAGMENT_UNIFORM_VECTORS),x=e.getParameter(e.MAX_SAMPLES),S=e.getParameter(e.SAMPLES);return{isWebGL2:!0,getMaxAnisotropy:a,getMaxPrecision:c,textureFormatReadable:o,textureTypeReadable:s,precision:l,logarithmicDepthBuffer:d,reversedDepthBuffer:f,maxTextures:p,maxVertexTextures:m,maxTextureSize:h,maxCubemapSize:g,maxAttributes:_,maxVertexUniforms:v,maxVaryings:y,maxFragmentUniforms:b,maxSamples:x,samples:S}}function If(e){let t=this,n=null,r=0,i=!1,a=!1,o=new _l,s=new Z,c={value:null,needsUpdate:!1};this.uniform=c,this.numPlanes=0,this.numIntersection=0,this.init=function(e,t){let n=e.length!==0||t||r!==0||i;return i=t,r=e.length,n},this.beginShadows=function(){a=!0,u(null)},this.endShadows=function(){a=!1},this.setGlobalState=function(e,t){n=u(e,t,0)},this.setState=function(t,o,s){let d=t.clippingPlanes,f=t.clipIntersection,p=t.clipShadows,m=e.get(t);if(!i||d===null||d.length===0||a&&!p)a?u(null):l();else{let e=a?0:r,t=e*4,i=m.clippingState||null;c.value=i,i=u(d,o,t,s);for(let e=0;e!==t;++e)i[e]=n[e];m.clippingState=i,this.numIntersection=f?this.numPlanes:0,this.numPlanes+=e}};function l(){c.value!==n&&(c.value=n,c.needsUpdate=r>0),t.numPlanes=r,t.numIntersection=0}function u(e,n,r,i){let a=e===null?0:e.length,l=null;if(a!==0){if(l=c.value,i!==!0||l===null){let t=r+a*4,i=n.matrixWorldInverse;s.getNormalMatrix(i),(l===null||l.length<t)&&(l=new Float32Array(t));for(let t=0,n=r;t!==a;++t,n+=4)o.copy(e[t]).applyMatrix4(i,s),o.normal.toArray(l,n),l[n+3]=o.constant}c.value=l,c.needsUpdate=!0}return t.numPlanes=a,t.numIntersection=0,l}}var Lf=4,Rf=6,zf=20,Bf=256,Vf=new Bd,Hf=new mc,Uf=null,Wf=0,Gf=0,Kf=!1,qf=new X,Jf=new X,Yf=class{constructor(e){this._renderer=e,this._pingPongRenderTarget=null,this._lodMax=0,this._cubeSize=0,this._sizeLods=[],this._lodMeshes=[],this._backgroundBox=null,this._cubemapMaterial=null,this._equirectMaterial=null,this._blurMaterial=null,this._ggxMaterial=null}fromScene(e,t=0,n=.1,r=100,i={}){let{size:a=256,position:o=qf}=i;Uf=this._renderer.getRenderTarget(),Wf=this._renderer.getActiveCubeFace(),Gf=this._renderer.getActiveMipmapLevel(),Kf=this._renderer.xr.enabled,this._renderer.xr.enabled=!1,this._setSize(a);let s=this._allocateTargets();return s.depthBuffer=!0,this._sceneToCubeUV(e,n,r,s,o),t>0&&this._blur(s,0,0,t),this._applyPMREM(s),this._cleanup(s),s}fromEquirectangular(e,t=null){return this._fromTexture(e,t)}fromCubemap(e,t=null){return this._fromTexture(e,t)}compileCubemapShader(){this._cubemapMaterial===null&&(this._cubemapMaterial=np(),this._compileMaterial(this._cubemapMaterial))}compileEquirectangularShader(){this._equirectMaterial===null&&(this._equirectMaterial=tp(),this._compileMaterial(this._equirectMaterial))}dispose(){this._dispose(),this._cubemapMaterial!==null&&this._cubemapMaterial.dispose(),this._equirectMaterial!==null&&this._equirectMaterial.dispose(),this._backgroundBox!==null&&(this._backgroundBox.geometry.dispose(),this._backgroundBox.material.dispose())}_setSize(e){this._lodMax=Math.floor(Math.log2(e)),this._cubeSize=2**this._lodMax}_dispose(){this._blurMaterial!==null&&this._blurMaterial.dispose(),this._ggxMaterial!==null&&this._ggxMaterial.dispose(),this._pingPongRenderTarget!==null&&this._pingPongRenderTarget.dispose();for(let e=0;e<this._lodMeshes.length;e++)this._lodMeshes[e].geometry.dispose()}_cleanup(e){this._renderer.setRenderTarget(Uf,Wf,Gf),this._renderer.xr.enabled=Kf,e.scissorTest=!1,Qf(e,0,0,e.width,e.height)}_fromTexture(e,t){e.mapping===301||e.mapping===302?this._setSize(e.image.length===0?16:e.image[0].width||e.image[0].image.width):this._setSize(e.image.width/4),Uf=this._renderer.getRenderTarget(),Wf=this._renderer.getActiveCubeFace(),Gf=this._renderer.getActiveMipmapLevel(),Kf=this._renderer.xr.enabled,this._renderer.xr.enabled=!1;let n=t||this._allocateTargets();return this._textureToCubeUV(e,n),this._applyPMREM(n),this._cleanup(n),n}_allocateTargets(){let e=3*Math.max(this._cubeSize,112),t=4*this._cubeSize,n={magFilter:ia,minFilter:ia,generateMipmaps:!1,type:ma,format:Sa,colorSpace:So,depthBuffer:!1},r=Zf(e,t,n);if(this._pingPongRenderTarget===null||this._pingPongRenderTarget.width!==e||this._pingPongRenderTarget.height!==t){this._pingPongRenderTarget!==null&&this._dispose(),this._pingPongRenderTarget=Zf(e,t,n);let{_lodMax:r}=this;({lodMeshes:this._lodMeshes,sizeLods:this._sizeLods}=Xf(r)),this._blurMaterial=ep(r,e,t),this._ggxMaterial=$f(r,e,t)}return r}_compileMaterial(e){let t=new Ll(new ul,e);this._renderer.compile(t,Vf)}_sceneToCubeUV(e,t,n,r,i){let a=new zd(90,1,t,n),o=[1,-1,1,1,1,1],s=[1,1,1,-1,-1,-1],c=this._renderer,l=c.autoClear,u=c.toneMapping;c.getClearColor(Hf),c.toneMapping=0,c.autoClear=!1,c.state.buffers.depth.getReversed()&&(c.setRenderTarget(r),c.clearDepth(),c.setRenderTarget(null)),this._backgroundBox===null&&(this._backgroundBox=new Ll(new gu,new Tl({name:`PMREM.Background`,side:1,depthWrite:!1,depthTest:!1})));let d=this._backgroundBox,f=d.material,p=!1,m=e.background;m?m.isColor&&(f.color.copy(m),e.background=null,p=!0):(f.color.copy(Hf),p=!0);for(let t=0;t<6;t++){let n=t%3;n===0?(a.up.set(0,o[t],0),a.position.set(i.x,i.y,i.z),a.lookAt(i.x+s[t],i.y,i.z)):n===1?(a.up.set(0,0,o[t]),a.position.set(i.x,i.y,i.z),a.lookAt(i.x,i.y+s[t],i.z)):(a.up.set(0,o[t],0),a.position.set(i.x,i.y,i.z),a.lookAt(i.x,i.y,i.z+s[t]));let l=this._cubeSize;Qf(r,n*l,t>2?l:0,l,l),c.setRenderTarget(r),p&&c.render(d,a),c.render(e,a)}c.toneMapping=u,c.autoClear=l,e.background=m}_textureToCubeUV(e,t){let n=this._renderer,r=e.mapping===301||e.mapping===302;r?(this._cubemapMaterial===null&&(this._cubemapMaterial=np()),this._cubemapMaterial.uniforms.flipEnvMap.value=e.isRenderTargetTexture===!1?-1:1):this._equirectMaterial===null&&(this._equirectMaterial=tp());let i=r?this._cubemapMaterial:this._equirectMaterial,a=this._lodMeshes[0];a.material=i;let o=i.uniforms;o.envMap.value=e;let s=this._cubeSize;Qf(t,0,0,3*s,2*s),n.setRenderTarget(t),n.render(a,Vf)}_applyPMREM(e){let t=this._renderer,n=t.autoClear;t.autoClear=!1;let r=this._lodMeshes.length;for(let t=1;t<r;t++)this._applyGGXFilter(e,t-1,t);t.autoClear=n}_applyGGXFilter(e,t,n){let r=this._renderer,i=this._pingPongRenderTarget,a=this._ggxMaterial,o=this._lodMeshes[n];o.material=a;let s=a.uniforms,c=n/(this._lodMeshes.length-1),l=t/(this._lodMeshes.length-1),u=Math.sqrt(c*c-l*l)*(c*1.25),{_lodMax:d}=this,f=this._sizeLods[n],p=3*f*(n>d-Lf?n-d+Lf:0),m=4*(this._cubeSize-f);s.envMap.value=e.texture,s.roughness.value=u,s.mipInt.value=d-t,Qf(i,p,m,3*f,2*f),r.setRenderTarget(i),r.render(o,Vf),s.envMap.value=i.texture,s.roughness.value=0,s.mipInt.value=d-n,Qf(e,p,m,3*f,2*f),r.setRenderTarget(e),r.render(o,Vf)}_blur(e,t,n,r){let i=this._pingPongRenderTarget,a=Math.min(r,Math.PI)/Math.SQRT2;this._blurPass(e,i,t,n,a),this._blurPass(i,e,n,n,a)}_blurPass(e,t,n,r,i){let a=this._renderer,o=this._blurMaterial,s=this._lodMeshes[r];s.material=o;let c=o.uniforms;c.envMap.value=e.texture,c.sigma.value=i,c.mipInt.value=this._lodMax-n;let l=this._sizeLods[r];Qf(t,3*l*(r>this._lodMax-Lf?r-this._lodMax+Lf:0),4*(this._cubeSize-l),3*l,2*l),a.setRenderTarget(t),a.render(s,Vf)}};function Xf(e){let t=[],n=[],r=e,i=e-Lf+1+Rf;for(let e=0;e<i;e++){let e=2**r;t.push(e);let i=1/(e-2),a=-i,o=1+i,s=[a,a,o,a,o,o,a,a,o,o,a,o],c=new Float32Array(108),l=new Float32Array(108);for(let e=0;e<6;e++){let t=e%3*2/3-1,n=e>2?0:-1,r=[t,n,0,t+2/3,n,0,t+2/3,n+1,0,t,n,0,t+2/3,n+1,0,t,n+1,0];c.set(r,18*e);for(let t=0;t<6;t++){let n=s[t*2]*2-1,r=s[t*2+1]*2-1;e===0?Jf.set(1,r,n):e===1?Jf.set(-n,1,-r):e===2?Jf.set(-n,r,1):e===3?Jf.set(-1,r,-n):e===4?Jf.set(-n,-1,r):Jf.set(n,r,-1),Jf.toArray(l,(e*6+t)*3)}}let u=new ul;u.setAttribute(`position`,new Yc(c,3)),u.setAttribute(`outputDirection`,new Yc(l,3)),n.push(new Ll(u,null)),r>Lf&&r--}return{lodMeshes:n,sizeLods:t}}function Zf(e,t,n){let r=new js(e,t,n);return r.texture.mapping=306,r.texture.name=`PMREM.cubeUv`,r.scissorTest=!0,r}function Qf(e,t,n,r,i){e.viewport.set(t,n,r,i),e.scissor.set(t,n,r,i)}function $f(e,t,n){return new rd({name:`PMREMGGXConvolution`,defines:{GGX_SAMPLES:Bf,CUBEUV_TEXEL_WIDTH:1/t,CUBEUV_TEXEL_HEIGHT:1/n,CUBEUV_MAX_MIP:`${e}.0`},uniforms:{envMap:{value:null},roughness:{value:0},mipInt:{value:0}},vertexShader:rp(),fragmentShader:`

			precision highp float;
			precision highp int;

			varying vec3 vOutputDirection;

			uniform sampler2D envMap;
			uniform float roughness;
			uniform float mipInt;

			#define ENVMAP_TYPE_CUBE_UV
			#include <cube_uv_reflection_fragment>

			#define PI 3.14159265359

			// Van der Corput radical inverse
			float radicalInverse_VdC(uint bits) {
				bits = (bits << 16u) | (bits >> 16u);
				bits = ((bits & 0x55555555u) << 1u) | ((bits & 0xAAAAAAAAu) >> 1u);
				bits = ((bits & 0x33333333u) << 2u) | ((bits & 0xCCCCCCCCu) >> 2u);
				bits = ((bits & 0x0F0F0F0Fu) << 4u) | ((bits & 0xF0F0F0F0u) >> 4u);
				bits = ((bits & 0x00FF00FFu) << 8u) | ((bits & 0xFF00FF00u) >> 8u);
				return float(bits) * 2.3283064365386963e-10; // / 0x100000000
			}

			// Hammersley sequence
			vec2 hammersley(uint i, uint N) {
				return vec2(float(i) / float(N), radicalInverse_VdC(i));
			}

			// GGX VNDF importance sampling (Eric Heitz 2018)
			// "Sampling the GGX Distribution of Visible Normals"
			// https://jcgt.org/published/0007/04/01/
			vec3 importanceSampleGGX_VNDF(vec2 Xi, vec3 V, float roughness) {
				float alpha = roughness * roughness;

				// Section 4.1: Orthonormal basis
				vec3 T1 = vec3(1.0, 0.0, 0.0);
				vec3 T2 = cross(V, T1);

				// Section 4.2: Parameterization of projected area
				float r = sqrt(Xi.x);
				float phi = 2.0 * PI * Xi.y;
				float t1 = r * cos(phi);
				float t2 = r * sin(phi);
				float s = 0.5 * (1.0 + V.z);
				t2 = (1.0 - s) * sqrt(1.0 - t1 * t1) + s * t2;

				// Section 4.3: Reprojection onto hemisphere
				vec3 Nh = t1 * T1 + t2 * T2 + sqrt(max(0.0, 1.0 - t1 * t1 - t2 * t2)) * V;

				// Section 3.4: Transform back to ellipsoid configuration
				return normalize(vec3(alpha * Nh.x, alpha * Nh.y, max(0.0, Nh.z)));
			}

			void main() {
				vec3 N = normalize(vOutputDirection);
				vec3 V = N; // Assume view direction equals normal for pre-filtering

				vec3 prefilteredColor = vec3(0.0);
				float totalWeight = 0.0;

				// For very low roughness, just sample the environment directly
				if (roughness < 0.001) {
					gl_FragColor = vec4(bilinearCubeUV(envMap, N, mipInt), 1.0);
					return;
				}

				// Tangent space basis for VNDF sampling
				vec3 up = abs(N.z) < 0.999 ? vec3(0.0, 0.0, 1.0) : vec3(1.0, 0.0, 0.0);
				vec3 tangent = normalize(cross(up, N));
				vec3 bitangent = cross(N, tangent);

				for(uint i = 0u; i < uint(GGX_SAMPLES); i++) {
					vec2 Xi = hammersley(i, uint(GGX_SAMPLES));

					// For PMREM, V = N, so in tangent space V is always (0, 0, 1)
					vec3 H_tangent = importanceSampleGGX_VNDF(Xi, vec3(0.0, 0.0, 1.0), roughness);

					// Transform H back to world space
					vec3 H = normalize(tangent * H_tangent.x + bitangent * H_tangent.y + N * H_tangent.z);
					vec3 L = normalize(2.0 * dot(V, H) * H - V);

					float NdotL = max(dot(N, L), 0.0);

					if(NdotL > 0.0) {
						// Sample environment at fixed mip level
						// VNDF importance sampling handles the distribution filtering
						vec3 sampleColor = bilinearCubeUV(envMap, L, mipInt);

						// Weight by NdotL for the split-sum approximation
						// VNDF PDF naturally accounts for the visible microfacet distribution
						prefilteredColor += sampleColor * NdotL;
						totalWeight += NdotL;
					}
				}

				if (totalWeight > 0.0) {
					prefilteredColor = prefilteredColor / totalWeight;
				}

				gl_FragColor = vec4(prefilteredColor, 1.0);
			}
		`,blending:0,depthTest:!1,depthWrite:!1})}function ep(e,t,n){return new rd({name:`SphericalGaussianBlur`,defines:{SAMPLES:zf,CUBEUV_TEXEL_WIDTH:1/t,CUBEUV_TEXEL_HEIGHT:1/n,CUBEUV_MAX_MIP:`${e}.0`},uniforms:{envMap:{value:null},sigma:{value:0},mipInt:{value:0}},vertexShader:rp(),fragmentShader:`

			precision highp float;
			precision highp int;

			varying vec3 vOutputDirection;

			uniform sampler2D envMap;
			uniform float sigma;
			uniform float mipInt;

			#define ENVMAP_TYPE_CUBE_UV
			#include <cube_uv_reflection_fragment>

			#define PI 3.14159265359
			#define GOLDEN_ANGLE 2.39996322973

			void main() {

				if ( sigma == 0.0 ) {

					gl_FragColor = vec4( bilinearCubeUV( envMap, vOutputDirection, mipInt ), 1.0 );
					return;

				}

				vec3 outputDirection = normalize( vOutputDirection );

				vec3 up = abs( outputDirection.z ) < 0.999 ? vec3( 0.0, 0.0, 1.0 ) : vec3( 1.0, 0.0, 0.0 );
				vec3 tangent = normalize( cross( up, outputDirection ) );
				vec3 bitangent = cross( outputDirection, tangent );

				// Truncate the kernel at three standard deviations or at the antipode.
				float thetaMax = min( 3.0 * sigma, PI );
				float truncation = 1.0 - exp( - 0.5 * thetaMax * thetaMax / ( sigma * sigma ) );

				vec3 accumColor = vec3( 0.0 );
				float accumWeight = 0.0;

				for ( int i = 0; i < SAMPLES; i ++ ) {

					// Stratified inverse-CDF sampling of the Gaussian, placed on a golden-angle spiral.
					float stratum = ( float( i ) + 0.5 ) / float( SAMPLES );
					float theta = sigma * sqrt( - 2.0 * log( 1.0 - stratum * truncation ) );
					float phi = float( i ) * GOLDEN_ANGLE;

					vec3 offset = cos( phi ) * tangent + sin( phi ) * bitangent;
					vec3 sampleDirection = cos( theta ) * outputDirection + sin( theta ) * offset;

					// Correct the planar sample density to solid angle.
					float weight = sin( theta ) / theta;

					accumColor += weight * bilinearCubeUV( envMap, sampleDirection, mipInt );
					accumWeight += weight;

				}

				gl_FragColor = vec4( accumColor / accumWeight, 1.0 );

			}
		`,blending:0,depthTest:!1,depthWrite:!1})}function tp(){return new rd({name:`EquirectangularToCubeUV`,uniforms:{envMap:{value:null}},vertexShader:rp(),fragmentShader:`

			precision mediump float;
			precision mediump int;

			varying vec3 vOutputDirection;

			uniform sampler2D envMap;

			#include <common>

			void main() {

				vec3 outputDirection = normalize( vOutputDirection );
				vec2 uv = equirectUv( outputDirection );

				gl_FragColor = vec4( texture2D ( envMap, uv ).rgb, 1.0 );

			}
		`,blending:0,depthTest:!1,depthWrite:!1})}function np(){return new rd({name:`CubemapToCubeUV`,uniforms:{envMap:{value:null},flipEnvMap:{value:-1}},vertexShader:rp(),fragmentShader:`

			precision mediump float;
			precision mediump int;

			uniform float flipEnvMap;

			varying vec3 vOutputDirection;

			uniform samplerCube envMap;

			void main() {

				gl_FragColor = textureCube( envMap, vec3( flipEnvMap * vOutputDirection.x, vOutputDirection.yz ) );

			}
		`,blending:0,depthTest:!1,depthWrite:!1})}function rp(){return`

		precision mediump float;
		precision mediump int;

		attribute vec3 outputDirection;

		varying vec3 vOutputDirection;

		void main() {

			vOutputDirection = outputDirection;
			gl_Position = vec4( position, 1.0 );

		}
	`}var ip=class extends js{constructor(e=1,t={}){super(e,e,t),this.isWebGLCubeRenderTarget=!0;let n={width:e,height:e,depth:1},r=[n,n,n,n,n,n];this.texture=new du(r),this._setTextureOptions(t),this.texture.isRenderTargetTexture=!0}fromEquirectangularTexture(e,t){this.texture.type=t.type,this.texture.colorSpace=t.colorSpace,this.texture.generateMipmaps=t.generateMipmaps,this.texture.minFilter=t.minFilter,this.texture.magFilter=t.magFilter;let n={uniforms:{tEquirect:{value:null}},vertexShader:`

				varying vec3 vWorldDirection;

				vec3 transformDirection( in vec3 dir, in mat4 matrix ) {

					return normalize( ( matrix * vec4( dir, 0.0 ) ).xyz );

				}

				void main() {

					vWorldDirection = transformDirection( position, modelMatrix );

					#include <begin_vertex>
					#include <project_vertex>

				}
			`,fragmentShader:`

				uniform sampler2D tEquirect;

				varying vec3 vWorldDirection;

				#include <common>

				void main() {

					vec3 direction = normalize( vWorldDirection );

					vec2 sampleUV = equirectUv( direction );

					gl_FragColor = texture2D( tEquirect, sampleUV );

				}
			`},r=new gu(5,5,5),i=new rd({name:`CubemapFromEquirect`,uniforms:Yu(n.uniforms),vertexShader:n.vertexShader,fragmentShader:n.fragmentShader,side:1,blending:0});i.uniforms.tEquirect.value=t;let a=new Ll(r,i),o=t.minFilter;return t.minFilter===1008&&(t.minFilter=ia),new qd(1,10,this).update(e,a),t.minFilter=o,a.geometry.dispose(),a.material.dispose(),this}clear(e,t=!0,n=!0,r=!0){let i=e.getRenderTarget();for(let i=0;i<6;i++)e.setRenderTarget(this,i),e.clear(t,n,r);e.setRenderTarget(i)}};function ap(e){let t=new WeakMap,n=new WeakMap,r=null;function i(e,t=!1){return e==null?null:t?o(e):a(e)}function a(n){if(n&&n.isTexture){let r=n.mapping;if(r===303||r===304){if(t.has(n)){let e=t.get(n).texture;return s(e,n.mapping)}{let r=n.image;if(r&&r.height>0){let i=new ip(r.height);return i.fromEquirectangularTexture(e,n),t.set(n,i),n.addEventListener(`dispose`,l),s(i.texture,n.mapping)}return null}}}return n}function o(t){if(t&&t.isTexture){let i=t.mapping,a=i===303||i===304,o=i===301||i===302;if(a||o){let i=n.get(t),s=i===void 0?0:i.texture.pmremVersion;if(t.isRenderTargetTexture&&t.pmremVersion!==s)return r===null&&(r=new Yf(e)),i=a?r.fromEquirectangular(t,i):r.fromCubemap(t,i),i.texture.pmremVersion=t.pmremVersion,n.set(t,i),i.texture;if(i!==void 0)return i.texture;{let s=t.image;return a&&s&&s.height>0||o&&s&&c(s)?(r===null&&(r=new Yf(e)),i=a?r.fromEquirectangular(t):r.fromCubemap(t),i.texture.pmremVersion=t.pmremVersion,n.set(t,i),t.addEventListener(`dispose`,u),i.texture):null}}}return t}function s(e,t){return t===303?e.mapping=301:t===304&&(e.mapping=302),e}function c(e){let t=0;for(let n=0;n<6;n++)e[n]!==void 0&&t++;return t===6}function l(e){let n=e.target;n.removeEventListener(`dispose`,l);let r=t.get(n);r!==void 0&&(t.delete(n),r.dispose())}function u(e){let t=e.target;t.removeEventListener(`dispose`,u);let r=n.get(t);r!==void 0&&(n.delete(t),r.dispose())}function d(){t=new WeakMap,n=new WeakMap,r!==null&&(r.dispose(),r=null)}return{get:i,dispose:d}}function op(e){let t={};function n(n){if(t[n]!==void 0)return t[n];let r=e.getExtension(n);return t[n]=r,r}return{has:function(e){return n(e)!==null},init:function(){n(`EXT_color_buffer_float`),n(`WEBGL_clip_cull_distance`),n(`OES_texture_float_linear`),n(`EXT_color_buffer_half_float`),n(`WEBGL_multisampled_render_to_texture`),n(`WEBGL_render_shared_exponent`)},get:function(e){let t=n(e);return t===null&&Fo(`WebGLRenderer: `+e+` extension not supported.`),t}}}function sp(e,t,n,r){let i={},a=new WeakMap;function o(e){let s=e.target;s.index!==null&&t.remove(s.index);for(let e in s.attributes)t.remove(s.attributes[e]);s.removeEventListener(`dispose`,o),delete i[s.id];let c=a.get(s);c&&(t.remove(c),a.delete(s)),r.releaseStatesOfGeometry(s),s.isInstancedBufferGeometry===!0&&delete s._maxInstanceCount,n.memory.geometries--}function s(e,t){return i[t.id]===!0?t:(t.addEventListener(`dispose`,o),i[t.id]=!0,n.memory.geometries++,t)}function c(n){let r=n.attributes;for(let n in r)t.update(r[n],e.ARRAY_BUFFER)}function l(e){let n=[],r=e.index,i=e.attributes.position,o=0;if(i===void 0)return;if(r!==null){let e=r.array;o=r.version;for(let t=0,r=e.length;t<r;t+=3){let r=e[t+0],i=e[t+1],a=e[t+2];n.push(r,i,i,a,a,r)}}else{let e=i.array;o=i.version;for(let t=0,r=e.length/3-1;t<r;t+=3){let e=t+0,r=t+1,i=t+2;n.push(e,r,r,i,i,e)}}let s=new(i.count>=65535?Zc:Xc)(n,1);s.version=o;let c=a.get(e);c&&t.remove(c),a.set(e,s)}function u(e){let t=a.get(e);if(t){let n=e.index;n!==null&&t.version<n.version&&l(e)}else l(e);return a.get(e)}return{get:s,update:c,getWireframeAttribute:u}}function cp(e,t,n){let r;function i(e){r=e}let a,o;function s(e){a=e.type,o=e.bytesPerElement}function c(t,i){e.drawElements(r,i,a,t*o),n.update(i,r,1)}function l(t,i,s){s!==0&&(e.drawElementsInstanced(r,i,a,t*o,s),n.update(i,r,s))}function u(e,i,o){if(o===0)return;t.get(`WEBGL_multi_draw`).multiDrawElementsWEBGL(r,i,0,a,e,0,o);let s=0;for(let e=0;e<o;e++)s+=i[e];n.update(s,r,1)}this.setMode=i,this.setIndex=s,this.render=c,this.renderInstances=l,this.renderMultiDraw=u}function lp(e){let t={geometries:0,textures:0},n={frame:0,calls:0,triangles:0,points:0,lines:0};function r(t,r,i){switch(n.calls++,r){case e.TRIANGLES:n.triangles+=t/3*i;break;case e.LINES:n.lines+=t/2*i;break;case e.LINE_STRIP:n.lines+=i*(t-1);break;case e.LINE_LOOP:n.lines+=i*t;break;case e.POINTS:n.points+=i*t;break;default:q(`WebGLInfo: Unknown draw mode:`,r)}}function i(){n.calls=0,n.triangles=0,n.points=0,n.lines=0}return{memory:t,render:n,programs:null,autoReset:!0,reset:i,update:r}}function up(e,t,n){let r=new WeakMap,i=new ks;function a(a,o,s){let c=a.morphTargetInfluences,l=o.morphAttributes.position||o.morphAttributes.normal||o.morphAttributes.color,u=l===void 0?0:l.length,d=r.get(o);if(d===void 0||d.count!==u){d!==void 0&&d.texture.dispose();let e=o.morphAttributes.position!==void 0,n=o.morphAttributes.normal!==void 0,a=o.morphAttributes.color!==void 0,s=o.morphAttributes.position||[],c=o.morphAttributes.normal||[],l=o.morphAttributes.color||[],f=0;e===!0&&(f=1),n===!0&&(f=2),a===!0&&(f=3);let p=o.attributes.position.count*f,m=1;p>t.maxTextureSize&&(m=Math.ceil(p/t.maxTextureSize),p=t.maxTextureSize);let h=new Float32Array(p*m*4*u),g=new Ms(h,p,m,u);g.type=pa,g.needsUpdate=!0;let _=f*4;for(let t=0;t<u;t++){let r=s[t],o=c[t],u=l[t],d=p*m*4*t;for(let t=0;t<r.count;t++){let s=t*_;e===!0&&(i.fromBufferAttribute(r,t),h[d+s+0]=i.x,h[d+s+1]=i.y,h[d+s+2]=i.z,h[d+s+3]=0),n===!0&&(i.fromBufferAttribute(o,t),h[d+s+4]=i.x,h[d+s+5]=i.y,h[d+s+6]=i.z,h[d+s+7]=0),a===!0&&(i.fromBufferAttribute(u,t),h[d+s+8]=i.x,h[d+s+9]=i.y,h[d+s+10]=i.z,h[d+s+11]=u.itemSize===4?i.w:1)}}d={count:u,texture:g,size:new Y(p,m)},r.set(o,d);function v(){g.dispose(),r.delete(o),o.removeEventListener(`dispose`,v)}o.addEventListener(`dispose`,v)}if(a.isInstancedMesh===!0&&a.morphTexture!==null)s.getUniforms().setValue(e,`morphTexture`,a.morphTexture,n);else{let t=0;for(let e=0;e<c.length;e++)t+=c[e];let n=o.morphTargetsRelative?1:1-t;s.getUniforms().setValue(e,`morphTargetBaseInfluence`,n),s.getUniforms().setValue(e,`morphTargetInfluences`,c)}s.getUniforms().setValue(e,`morphTargetsTexture`,d.texture,n),s.getUniforms().setValue(e,`morphTargetsTextureSize`,d.size)}return{update:a}}function dp(e,t,n,r,i){let a=new WeakMap;function o(r){let o=i.render.frame,s=r.geometry,l=t.get(r,s);if(a.get(l)!==o&&(t.update(l),a.set(l,o)),r.isInstancedMesh&&(r.hasEventListener(`dispose`,c)===!1&&r.addEventListener(`dispose`,c),a.get(r)!==o&&(n.update(r.instanceMatrix,e.ARRAY_BUFFER),r.instanceColor!==null&&n.update(r.instanceColor,e.ARRAY_BUFFER),a.set(r,o))),r.isSkinnedMesh){let e=r.skeleton;a.get(e)!==o&&(e.update(),a.set(e,o))}return l}function s(){a=new WeakMap}function c(e){let t=e.target;t.removeEventListener(`dispose`,c),r.releaseStatesOfObject(t),n.remove(t.instanceMatrix),t.instanceColor!==null&&n.remove(t.instanceColor)}return{update:o,dispose:s}}var fp={1:`LINEAR_TONE_MAPPING`,2:`REINHARD_TONE_MAPPING`,3:`CINEON_TONE_MAPPING`,4:`ACES_FILMIC_TONE_MAPPING`,6:`AGX_TONE_MAPPING`,7:`NEUTRAL_TONE_MAPPING`,5:`CUSTOM_TONE_MAPPING`};function pp(e,t,n,r,i,a){let o=new js(t,n,{type:e,depthBuffer:i,stencilBuffer:a,samples:r?4:0,storeMultisampledDepthBuffer:!1,storeMultisampledStencilBuffer:!1,resolveDepthBuffer:!1,resolveStencilBuffer:!1}),s=null,c=null,l=new ul;l.setAttribute(`position`,new Qc([-1,3,0,-1,-1,0,3,-1,0],3)),l.setAttribute(`uv`,new Qc([0,2,0,0,2,0],2));let u=new id({uniforms:{tDiffuse:{value:null}},vertexShader:`
			precision highp float;

			uniform mat4 modelViewMatrix;
			uniform mat4 projectionMatrix;

			attribute vec3 position;
			attribute vec2 uv;

			varying vec2 vUv;

			void main() {
				vUv = uv;
				gl_Position = projectionMatrix * modelViewMatrix * vec4( position, 1.0 );
			}`,fragmentShader:`
			precision highp float;

			uniform sampler2D tDiffuse;

			varying vec2 vUv;

			#include <tonemapping_pars_fragment>
			#include <colorspace_pars_fragment>

			void main() {
				gl_FragColor = texture2D( tDiffuse, vUv );

				#ifdef LINEAR_TONE_MAPPING
					gl_FragColor.rgb = LinearToneMapping( gl_FragColor.rgb );
				#elif defined( REINHARD_TONE_MAPPING )
					gl_FragColor.rgb = ReinhardToneMapping( gl_FragColor.rgb );
				#elif defined( CINEON_TONE_MAPPING )
					gl_FragColor.rgb = CineonToneMapping( gl_FragColor.rgb );
				#elif defined( ACES_FILMIC_TONE_MAPPING )
					gl_FragColor.rgb = ACESFilmicToneMapping( gl_FragColor.rgb );
				#elif defined( AGX_TONE_MAPPING )
					gl_FragColor.rgb = AgXToneMapping( gl_FragColor.rgb );
				#elif defined( NEUTRAL_TONE_MAPPING )
					gl_FragColor.rgb = NeutralToneMapping( gl_FragColor.rgb );
				#elif defined( CUSTOM_TONE_MAPPING )
					gl_FragColor.rgb = CustomToneMapping( gl_FragColor.rgb );
				#endif

				#ifdef SRGB_TRANSFER
					gl_FragColor = sRGBTransferOETF( gl_FragColor );
				#endif
			}`,depthTest:!1,depthWrite:!1}),d=new Ll(l,u),f=new Bd(-1,1,1,-1,0,1),p=null,m=null,h=!1,g,_=null,v=[],y=!1;this.setSize=function(e,t){o.setSize(e,t),s!==null&&s.setSize(e,t),c!==null&&c.setSize(e,t);for(let n=0;n<v.length;n++){let r=v[n];r.setSize&&r.setSize(e,t)}},this.setEffects=function(e){v=e,y=v.length>0&&v[0].isRenderPass===!0;let t=o.width,n=o.height;v.length>0&&s===null&&(s=new js(t,n,{type:ma,depthBuffer:!1,stencilBuffer:!1}),c=new js(t,n,{type:ma,depthBuffer:!1,stencilBuffer:!1}));for(let e=0;e<v.length;e++){let r=v[e];r.setSize&&r.setSize(t,n)}},this.begin=function(e,t){if(h||e.toneMapping===0&&v.length===0)return!1;if(_=t,t!==null){let e=t.width,n=t.height;(o.width!==e||o.height!==n)&&this.setSize(e,n)}return y===!1&&e.setRenderTarget(o),g=e.toneMapping,e.toneMapping=0,!0},this.hasRenderPass=function(){return y},this.end=function(e,t){e.toneMapping=g,h=!0;let n=o,r=s;for(let i=0;i<v.length;i++){let a=v[i];a.enabled!==!1&&(a.render(e,r,n,t),a.needsSwap!==!1&&(n=r,r=r===s?c:s))}if(p!==e.outputColorSpace||m!==e.toneMapping){p=e.outputColorSpace,m=e.toneMapping,u.defines={},vs.getTransfer(p)===`srgb`&&(u.defines.SRGB_TRANSFER=``);let t=fp[m];t&&(u.defines[t]=``),u.needsUpdate=!0}u.uniforms.tDiffuse.value=n.texture,e.setRenderTarget(_),e.render(d,f),_=null,h=!1},this.isCompositing=function(){return h},this.dispose=function(){o.dispose(),s!==null&&s.dispose(),c!==null&&c.dispose(),l.dispose(),u.dispose()}}var mp=new Os,hp=new pu(1,1),gp=new Ms,_p=new Ns,vp=new du,yp=[],bp=[],xp=new Float32Array(16),Sp=new Float32Array(9),Cp=new Float32Array(4);function wp(e,t,n){let r=e[0];if(r<=0||r>0)return e;let i=t*n,a=yp[i];if(a===void 0&&(a=new Float32Array(i),yp[i]=a),t!==0){r.toArray(a,0);for(let r=1,i=0;r!==t;++r)i+=n,e[r].toArray(a,i)}return a}function Tp(e,t){if(e.length!==t.length)return!1;for(let n=0,r=e.length;n<r;n++)if(e[n]!==t[n])return!1;return!0}function Ep(e,t){for(let n=0,r=t.length;n<r;n++)e[n]=t[n]}function Dp(e,t){let n=bp[t];n===void 0&&(n=new Int32Array(t),bp[t]=n);for(let r=0;r!==t;++r)n[r]=e.allocateTextureUnit();return n}function Op(e,t){let n=this.cache;n[0]!==t&&(e.uniform1f(this.addr,t),n[0]=t)}function kp(e,t){let n=this.cache;if(t.x!==void 0)(n[0]!==t.x||n[1]!==t.y)&&(e.uniform2f(this.addr,t.x,t.y),n[0]=t.x,n[1]=t.y);else{if(Tp(n,t))return;e.uniform2fv(this.addr,t),Ep(n,t)}}function Ap(e,t){let n=this.cache;if(t.x!==void 0)(n[0]!==t.x||n[1]!==t.y||n[2]!==t.z)&&(e.uniform3f(this.addr,t.x,t.y,t.z),n[0]=t.x,n[1]=t.y,n[2]=t.z);else if(t.r!==void 0)(n[0]!==t.r||n[1]!==t.g||n[2]!==t.b)&&(e.uniform3f(this.addr,t.r,t.g,t.b),n[0]=t.r,n[1]=t.g,n[2]=t.b);else{if(Tp(n,t))return;e.uniform3fv(this.addr,t),Ep(n,t)}}function jp(e,t){let n=this.cache;if(t.x!==void 0)(n[0]!==t.x||n[1]!==t.y||n[2]!==t.z||n[3]!==t.w)&&(e.uniform4f(this.addr,t.x,t.y,t.z,t.w),n[0]=t.x,n[1]=t.y,n[2]=t.z,n[3]=t.w);else{if(Tp(n,t))return;e.uniform4fv(this.addr,t),Ep(n,t)}}function Mp(e,t){let n=this.cache,r=t.elements;if(r===void 0){if(Tp(n,t))return;e.uniformMatrix2fv(this.addr,!1,t),Ep(n,t)}else{if(Tp(n,r))return;Cp.set(r),e.uniformMatrix2fv(this.addr,!1,Cp),Ep(n,r)}}function Np(e,t){let n=this.cache,r=t.elements;if(r===void 0){if(Tp(n,t))return;e.uniformMatrix3fv(this.addr,!1,t),Ep(n,t)}else{if(Tp(n,r))return;Sp.set(r),e.uniformMatrix3fv(this.addr,!1,Sp),Ep(n,r)}}function Pp(e,t){let n=this.cache,r=t.elements;if(r===void 0){if(Tp(n,t))return;e.uniformMatrix4fv(this.addr,!1,t),Ep(n,t)}else{if(Tp(n,r))return;xp.set(r),e.uniformMatrix4fv(this.addr,!1,xp),Ep(n,r)}}function Fp(e,t){let n=this.cache;n[0]!==t&&(e.uniform1i(this.addr,t),n[0]=t)}function Ip(e,t){let n=this.cache;if(t.x!==void 0)(n[0]!==t.x||n[1]!==t.y)&&(e.uniform2i(this.addr,t.x,t.y),n[0]=t.x,n[1]=t.y);else{if(Tp(n,t))return;e.uniform2iv(this.addr,t),Ep(n,t)}}function Lp(e,t){let n=this.cache;if(t.x!==void 0)(n[0]!==t.x||n[1]!==t.y||n[2]!==t.z)&&(e.uniform3i(this.addr,t.x,t.y,t.z),n[0]=t.x,n[1]=t.y,n[2]=t.z);else{if(Tp(n,t))return;e.uniform3iv(this.addr,t),Ep(n,t)}}function Rp(e,t){let n=this.cache;if(t.x!==void 0)(n[0]!==t.x||n[1]!==t.y||n[2]!==t.z||n[3]!==t.w)&&(e.uniform4i(this.addr,t.x,t.y,t.z,t.w),n[0]=t.x,n[1]=t.y,n[2]=t.z,n[3]=t.w);else{if(Tp(n,t))return;e.uniform4iv(this.addr,t),Ep(n,t)}}function zp(e,t){let n=this.cache;n[0]!==t&&(e.uniform1ui(this.addr,t),n[0]=t)}function Bp(e,t){let n=this.cache;if(t.x!==void 0)(n[0]!==t.x||n[1]!==t.y)&&(e.uniform2ui(this.addr,t.x,t.y),n[0]=t.x,n[1]=t.y);else{if(Tp(n,t))return;e.uniform2uiv(this.addr,t),Ep(n,t)}}function Vp(e,t){let n=this.cache;if(t.x!==void 0)(n[0]!==t.x||n[1]!==t.y||n[2]!==t.z)&&(e.uniform3ui(this.addr,t.x,t.y,t.z),n[0]=t.x,n[1]=t.y,n[2]=t.z);else{if(Tp(n,t))return;e.uniform3uiv(this.addr,t),Ep(n,t)}}function Hp(e,t){let n=this.cache;if(t.x!==void 0)(n[0]!==t.x||n[1]!==t.y||n[2]!==t.z||n[3]!==t.w)&&(e.uniform4ui(this.addr,t.x,t.y,t.z,t.w),n[0]=t.x,n[1]=t.y,n[2]=t.z,n[3]=t.w);else{if(Tp(n,t))return;e.uniform4uiv(this.addr,t),Ep(n,t)}}function Up(e,t,n){let r=this.cache,i=n.allocateTextureUnit();r[0]!==i&&(e.uniform1i(this.addr,i),r[0]=i);let a;this.type===e.SAMPLER_2D_SHADOW?(hp.compareFunction=n.isReversedDepthBuffer()?518:515,a=hp):a=mp,n.setTexture2D(t||a,i)}function Wp(e,t,n){let r=this.cache,i=n.allocateTextureUnit();r[0]!==i&&(e.uniform1i(this.addr,i),r[0]=i),n.setTexture3D(t||_p,i)}function Gp(e,t,n){let r=this.cache,i=n.allocateTextureUnit();r[0]!==i&&(e.uniform1i(this.addr,i),r[0]=i),n.setTextureCube(t||vp,i)}function Kp(e,t,n){let r=this.cache,i=n.allocateTextureUnit();r[0]!==i&&(e.uniform1i(this.addr,i),r[0]=i),n.setTexture2DArray(t||gp,i)}function qp(e){switch(e){case 5126:return Op;case 35664:return kp;case 35665:return Ap;case 35666:return jp;case 35674:return Mp;case 35675:return Np;case 35676:return Pp;case 5124:case 35670:return Fp;case 35667:case 35671:return Ip;case 35668:case 35672:return Lp;case 35669:case 35673:return Rp;case 5125:return zp;case 36294:return Bp;case 36295:return Vp;case 36296:return Hp;case 35678:case 36198:case 36298:case 36306:case 35682:return Up;case 35679:case 36299:case 36307:return Wp;case 35680:case 36300:case 36308:case 36293:return Gp;case 36289:case 36303:case 36311:case 36292:return Kp}}function Jp(e,t){e.uniform1fv(this.addr,t)}function Yp(e,t){let n=wp(t,this.size,2);e.uniform2fv(this.addr,n)}function Xp(e,t){let n=wp(t,this.size,3);e.uniform3fv(this.addr,n)}function Zp(e,t){let n=wp(t,this.size,4);e.uniform4fv(this.addr,n)}function Qp(e,t){let n=wp(t,this.size,4);e.uniformMatrix2fv(this.addr,!1,n)}function $p(e,t){let n=wp(t,this.size,9);e.uniformMatrix3fv(this.addr,!1,n)}function em(e,t){let n=wp(t,this.size,16);e.uniformMatrix4fv(this.addr,!1,n)}function tm(e,t){e.uniform1iv(this.addr,t)}function nm(e,t){e.uniform2iv(this.addr,t)}function rm(e,t){e.uniform3iv(this.addr,t)}function im(e,t){e.uniform4iv(this.addr,t)}function am(e,t){e.uniform1uiv(this.addr,t)}function om(e,t){e.uniform2uiv(this.addr,t)}function sm(e,t){e.uniform3uiv(this.addr,t)}function cm(e,t){e.uniform4uiv(this.addr,t)}function lm(e,t,n){let r=this.cache,i=t.length,a=Dp(n,i);Tp(r,a)||(e.uniform1iv(this.addr,a),Ep(r,a));let o;o=this.type===e.SAMPLER_2D_SHADOW?hp:mp;for(let e=0;e!==i;++e)n.setTexture2D(t[e]||o,a[e])}function um(e,t,n){let r=this.cache,i=t.length,a=Dp(n,i);Tp(r,a)||(e.uniform1iv(this.addr,a),Ep(r,a));for(let e=0;e!==i;++e)n.setTexture3D(t[e]||_p,a[e])}function dm(e,t,n){let r=this.cache,i=t.length,a=Dp(n,i);Tp(r,a)||(e.uniform1iv(this.addr,a),Ep(r,a));for(let e=0;e!==i;++e)n.setTextureCube(t[e]||vp,a[e])}function fm(e,t,n){let r=this.cache,i=t.length,a=Dp(n,i);Tp(r,a)||(e.uniform1iv(this.addr,a),Ep(r,a));for(let e=0;e!==i;++e)n.setTexture2DArray(t[e]||gp,a[e])}function pm(e){switch(e){case 5126:return Jp;case 35664:return Yp;case 35665:return Xp;case 35666:return Zp;case 35674:return Qp;case 35675:return $p;case 35676:return em;case 5124:case 35670:return tm;case 35667:case 35671:return nm;case 35668:case 35672:return rm;case 35669:case 35673:return im;case 5125:return am;case 36294:return om;case 36295:return sm;case 36296:return cm;case 35678:case 36198:case 36298:case 36306:case 35682:return lm;case 35679:case 36299:case 36307:return um;case 35680:case 36300:case 36308:case 36293:return dm;case 36289:case 36303:case 36311:case 36292:return fm}}var mm=class{constructor(e,t,n){this.id=e,this.addr=n,this.cache=[],this.type=t.type,this.setValue=qp(t.type)}},hm=class{constructor(e,t,n){this.id=e,this.addr=n,this.cache=[],this.type=t.type,this.size=t.size,this.setValue=pm(t.type)}},gm=class{constructor(e){this.id=e,this.seq=[],this.map={}}setValue(e,t,n){let r=this.seq;for(let i=0,a=r.length;i!==a;++i){let a=r[i];a.setValue(e,t[a.id],n)}}},_m=/(\w+)(\])?(\[|\.)?/g;function vm(e,t){e.seq.push(t),e.map[t.id]=t}function ym(e,t,n){let r=e.name,i=r.length;for(_m.lastIndex=0;;){let a=_m.exec(r),o=_m.lastIndex,s=a[1],c=a[2]===`]`,l=a[3];if(c&&(s|=0),l===void 0||l===`[`&&o+2===i){vm(n,l===void 0?new mm(s,e,t):new hm(s,e,t));break}{let e=n.map[s];e===void 0&&(e=new gm(s),vm(n,e)),n=e}}}var bm=class{constructor(e,t){this.seq=[],this.map={};let n=e.getProgramParameter(t,e.ACTIVE_UNIFORMS);for(let r=0;r<n;++r){let n=e.getActiveUniform(t,r);ym(n,e.getUniformLocation(t,n.name),this)}let r=[],i=[];for(let t of this.seq)t.type===e.SAMPLER_2D_SHADOW||t.type===e.SAMPLER_CUBE_SHADOW||t.type===e.SAMPLER_2D_ARRAY_SHADOW?r.push(t):i.push(t);r.length>0&&(this.seq=r.concat(i))}setValue(e,t,n,r){let i=this.map[t];i!==void 0&&i.setValue(e,n,r)}setOptional(e,t,n){let r=t[n];r!==void 0&&this.setValue(e,n,r)}static upload(e,t,n,r){for(let i=0,a=t.length;i!==a;++i){let a=t[i],o=n[a.id];o.needsUpdate!==!1&&a.setValue(e,o.value,r)}}static seqWithValue(e,t){let n=[];for(let r=0,i=e.length;r!==i;++r){let i=e[r];i.id in t&&n.push(i)}return n}};function xm(e,t,n){let r=e.createShader(t);return e.shaderSource(r,n),e.compileShader(r),r}var Sm=37297,Cm=0;function wm(e,t){let n=e.split(`
`),r=[],i=Math.max(t-6,0),a=Math.min(t+6,n.length);for(let e=i;e<a;e++){let i=e+1;r.push(`${i===t?`>`:` `} ${i}: ${n[e]}`)}return r.join(`
`)}var Tm=new Z;function Em(e){vs._getMatrix(Tm,vs.workingColorSpace,e);let t=`mat3( ${Tm.elements.map(e=>e.toFixed(4))} )`;switch(vs.getTransfer(e)){case Co:return[t,`LinearTransferOETF`];case wo:return[t,`sRGBTransferOETF`];default:return K(`WebGLProgram: Unsupported color space: `,e),[t,`LinearTransferOETF`]}}function Dm(e,t,n){let r=e.getShaderParameter(t,e.COMPILE_STATUS),i=(e.getShaderInfoLog(t)||``).trim();if(r&&i===``)return``;let a=/ERROR: 0:(\d+)/.exec(i);if(a){let r=parseInt(a[1]);return n.toUpperCase()+`

`+i+`

`+wm(e.getShaderSource(t),r)}return i}function Om(e,t){let n=Em(t);return[`vec4 ${e}( vec4 value ) {`,`	return ${n[1]}( vec4( value.rgb * ${n[0]}, value.a ) );`,`}`].join(`
`)}var km={1:`Linear`,2:`Reinhard`,3:`Cineon`,4:`ACESFilmic`,6:`AgX`,7:`Neutral`,5:`Custom`};function Am(e,t){let n=km[t];return n===void 0?(K(`WebGLProgram: Unsupported toneMapping:`,t),`vec3 `+e+`( vec3 color ) { return LinearToneMapping( color ); }`):`vec3 `+e+`( vec3 color ) { return `+n+`ToneMapping( color ); }`}var jm=new X;function Mm(){return vs.getLuminanceCoefficients(jm),[`float luminance( const in vec3 rgb ) {`,`	const vec3 weights = vec3( ${jm.x.toFixed(4)}, ${jm.y.toFixed(4)}, ${jm.z.toFixed(4)} );`,`	return dot( weights, rgb );`,`}`].join(`
`)}function Nm(e){return[e.extensionClipCullDistance?`#extension GL_ANGLE_clip_cull_distance : require`:``,e.extensionMultiDraw?`#extension GL_ANGLE_multi_draw : require`:``].filter(Im).join(`
`)}function Pm(e){let t=[];for(let n in e){let r=e[n];r!==!1&&t.push(`#define `+n+` `+r)}return t.join(`
`)}function Fm(e,t){let n={},r=e.getProgramParameter(t,e.ACTIVE_ATTRIBUTES);for(let i=0;i<r;i++){let r=e.getActiveAttrib(t,i),a=r.name,o=1;r.type===e.FLOAT_MAT2&&(o=2),r.type===e.FLOAT_MAT3&&(o=3),r.type===e.FLOAT_MAT4&&(o=4),n[a]={type:r.type,location:e.getAttribLocation(t,a),locationSize:o}}return n}function Im(e){return e!==``}function Lm(e,t){let n=t.numSpotLightShadows+t.numSpotLightMaps-t.numSpotLightShadowsWithMaps;return e.replace(/NUM_SUN_LIGHTS/g,t.numSunLights).replace(/NUM_DIR_LIGHTS/g,t.numDirLights).replace(/NUM_SPOT_LIGHTS/g,t.numSpotLights).replace(/NUM_SPOT_LIGHT_MAPS/g,t.numSpotLightMaps).replace(/NUM_SPOT_LIGHT_COORDS/g,n).replace(/NUM_RECT_AREA_LIGHTS/g,t.numRectAreaLights).replace(/NUM_POINT_LIGHTS/g,t.numPointLights).replace(/NUM_HEMI_LIGHTS/g,t.numHemiLights).replace(/NUM_SUN_LIGHT_SHADOWS/g,t.numSunLightShadows).replace(/NUM_DIR_LIGHT_SHADOWS/g,t.numDirLightShadows).replace(/NUM_SPOT_LIGHT_SHADOWS_WITH_MAPS/g,t.numSpotLightShadowsWithMaps).replace(/NUM_SPOT_LIGHT_SHADOWS/g,t.numSpotLightShadows).replace(/NUM_POINT_LIGHT_SHADOWS/g,t.numPointLightShadows)}function Rm(e,t){return e.replace(/NUM_CLIPPING_PLANES/g,t.numClippingPlanes).replace(/UNION_CLIPPING_PLANES/g,t.numClippingPlanes-t.numClipIntersection)}var zm=/^[ \t]*#include +<([\w\d./]+)>/gm;function Bm(e){return e.replace(zm,Hm)}var Vm=new Map;function Hm(e,t){let n=Df[t];if(n===void 0){let e=Vm.get(t);if(e!==void 0)n=Df[e],K(`WebGLRenderer: Shader chunk "%s" has been deprecated. Use "%s" instead.`,t,e);else throw Error(`THREE.WebGLProgram: Can not resolve #include <`+t+`>`)}return Bm(n)}var Um=/#pragma unroll_loop_start\s+for\s*\(\s*int\s+i\s*=\s*(\d+)\s*;\s*i\s*<\s*(\d+)\s*;\s*i\s*\+\+\s*\)\s*{([\s\S]+?)}\s+#pragma unroll_loop_end/g;function Wm(e){return e.replace(Um,Gm)}function Gm(e,t,n,r){let i=``;for(let e=parseInt(t);e<parseInt(n);e++)i+=r.replace(/\[\s*i\s*\]/g,`[ `+e+` ]`).replace(/UNROLLED_LOOP_INDEX/g,e);return i}function Km(e){let t=`precision ${e.precision} float;
	precision ${e.precision} int;
	precision ${e.precision} sampler2D;
	precision ${e.precision} samplerCube;
	precision ${e.precision} sampler3D;
	precision ${e.precision} sampler2DArray;
	precision ${e.precision} sampler2DShadow;
	precision ${e.precision} samplerCubeShadow;
	precision ${e.precision} sampler2DArrayShadow;
	precision ${e.precision} isampler2D;
	precision ${e.precision} isampler3D;
	precision ${e.precision} isamplerCube;
	precision ${e.precision} isampler2DArray;
	precision ${e.precision} usampler2D;
	precision ${e.precision} usampler3D;
	precision ${e.precision} usamplerCube;
	precision ${e.precision} usampler2DArray;
	`;return e.precision===`highp`?t+=`
#define HIGH_PRECISION`:e.precision===`mediump`?t+=`
#define MEDIUM_PRECISION`:e.precision===`lowp`&&(t+=`
#define LOW_PRECISION`),t}var qm={1:`SHADOWMAP_TYPE_PCF`,3:`SHADOWMAP_TYPE_VSM`};function Jm(e){return qm[e.shadowMapType]||`SHADOWMAP_TYPE_BASIC`}var Ym={301:`ENVMAP_TYPE_CUBE`,302:`ENVMAP_TYPE_CUBE`,306:`ENVMAP_TYPE_CUBE_UV`};function Xm(e){return e.envMap===!1?`ENVMAP_TYPE_CUBE`:Ym[e.envMapMode]||`ENVMAP_TYPE_CUBE`}var Zm={302:`ENVMAP_MODE_REFRACTION`};function Qm(e){return e.envMap===!1?`ENVMAP_MODE_REFLECTION`:Zm[e.envMapMode]||`ENVMAP_MODE_REFLECTION`}var $m={0:`ENVMAP_BLENDING_MULTIPLY`,1:`ENVMAP_BLENDING_MIX`,2:`ENVMAP_BLENDING_ADD`};function eh(e){return e.envMap===!1?`ENVMAP_BLENDING_NONE`:$m[e.combine]||`ENVMAP_BLENDING_NONE`}function th(e){let t=e.envMapCubeUVHeight;if(t===null)return null;let n=Math.log2(t)-2,r=1/t;return{texelWidth:1/(3*Math.max(2**n,112)),texelHeight:r,maxMip:n}}function nh(e,t,n,r){let i=e.getContext(),a=n.defines,o=n.vertexShader,s=n.fragmentShader,c=Jm(n),l=Xm(n),u=Qm(n),d=eh(n),f=th(n),p=Nm(n),m=Pm(a),h=i.createProgram(),g,_,v=n.glslVersion?`#version `+n.glslVersion+`
`:``;n.isRawShaderMaterial?(g=[`#define SHADER_TYPE `+n.shaderType,`#define SHADER_NAME `+n.shaderName,m].filter(Im).join(`
`),g.length>0&&(g+=`
`),_=[`#define SHADER_TYPE `+n.shaderType,`#define SHADER_NAME `+n.shaderName,m].filter(Im).join(`
`),_.length>0&&(_+=`
`)):(g=[Km(n),`#define SHADER_TYPE `+n.shaderType,`#define SHADER_NAME `+n.shaderName,m,n.extensionClipCullDistance?`#define USE_CLIP_DISTANCE`:``,n.batching?`#define USE_BATCHING`:``,n.batchingColor?`#define USE_BATCHING_COLOR`:``,n.instancing?`#define USE_INSTANCING`:``,n.instancingColor?`#define USE_INSTANCING_COLOR`:``,n.instancingMorph?`#define USE_INSTANCING_MORPH`:``,n.useFog&&n.fog?`#define USE_FOG`:``,n.useFog&&n.fogExp2?`#define FOG_EXP2`:``,n.map?`#define USE_MAP`:``,n.envMap?`#define USE_ENVMAP`:``,n.envMap?`#define `+u:``,n.lightMap?`#define USE_LIGHTMAP`:``,n.aoMap?`#define USE_AOMAP`:``,n.bumpMap?`#define USE_BUMPMAP`:``,n.normalMap?`#define USE_NORMALMAP`:``,n.normalMapObjectSpace?`#define USE_NORMALMAP_OBJECTSPACE`:``,n.normalMapTangentSpace?`#define USE_NORMALMAP_TANGENTSPACE`:``,n.displacementMap?`#define USE_DISPLACEMENTMAP`:``,n.emissiveMap?`#define USE_EMISSIVEMAP`:``,n.anisotropy?`#define USE_ANISOTROPY`:``,n.anisotropyMap?`#define USE_ANISOTROPYMAP`:``,n.clearcoatMap?`#define USE_CLEARCOATMAP`:``,n.clearcoatRoughnessMap?`#define USE_CLEARCOAT_ROUGHNESSMAP`:``,n.clearcoatNormalMap?`#define USE_CLEARCOAT_NORMALMAP`:``,n.iridescenceMap?`#define USE_IRIDESCENCEMAP`:``,n.iridescenceThicknessMap?`#define USE_IRIDESCENCE_THICKNESSMAP`:``,n.specularMap?`#define USE_SPECULARMAP`:``,n.specularColorMap?`#define USE_SPECULAR_COLORMAP`:``,n.specularIntensityMap?`#define USE_SPECULAR_INTENSITYMAP`:``,n.roughnessMap?`#define USE_ROUGHNESSMAP`:``,n.metalnessMap?`#define USE_METALNESSMAP`:``,n.alphaMap?`#define USE_ALPHAMAP`:``,n.alphaHash?`#define USE_ALPHAHASH`:``,n.transmission?`#define USE_TRANSMISSION`:``,n.transmissionMap?`#define USE_TRANSMISSIONMAP`:``,n.thicknessMap?`#define USE_THICKNESSMAP`:``,n.sheenColorMap?`#define USE_SHEEN_COLORMAP`:``,n.sheenRoughnessMap?`#define USE_SHEEN_ROUGHNESSMAP`:``,n.mapUv?`#define MAP_UV `+n.mapUv:``,n.alphaMapUv?`#define ALPHAMAP_UV `+n.alphaMapUv:``,n.lightMapUv?`#define LIGHTMAP_UV `+n.lightMapUv:``,n.aoMapUv?`#define AOMAP_UV `+n.aoMapUv:``,n.emissiveMapUv?`#define EMISSIVEMAP_UV `+n.emissiveMapUv:``,n.bumpMapUv?`#define BUMPMAP_UV `+n.bumpMapUv:``,n.normalMapUv?`#define NORMALMAP_UV `+n.normalMapUv:``,n.displacementMapUv?`#define DISPLACEMENTMAP_UV `+n.displacementMapUv:``,n.metalnessMapUv?`#define METALNESSMAP_UV `+n.metalnessMapUv:``,n.roughnessMapUv?`#define ROUGHNESSMAP_UV `+n.roughnessMapUv:``,n.anisotropyMapUv?`#define ANISOTROPYMAP_UV `+n.anisotropyMapUv:``,n.clearcoatMapUv?`#define CLEARCOATMAP_UV `+n.clearcoatMapUv:``,n.clearcoatNormalMapUv?`#define CLEARCOAT_NORMALMAP_UV `+n.clearcoatNormalMapUv:``,n.clearcoatRoughnessMapUv?`#define CLEARCOAT_ROUGHNESSMAP_UV `+n.clearcoatRoughnessMapUv:``,n.iridescenceMapUv?`#define IRIDESCENCEMAP_UV `+n.iridescenceMapUv:``,n.iridescenceThicknessMapUv?`#define IRIDESCENCE_THICKNESSMAP_UV `+n.iridescenceThicknessMapUv:``,n.sheenColorMapUv?`#define SHEEN_COLORMAP_UV `+n.sheenColorMapUv:``,n.sheenRoughnessMapUv?`#define SHEEN_ROUGHNESSMAP_UV `+n.sheenRoughnessMapUv:``,n.specularMapUv?`#define SPECULARMAP_UV `+n.specularMapUv:``,n.specularColorMapUv?`#define SPECULAR_COLORMAP_UV `+n.specularColorMapUv:``,n.specularIntensityMapUv?`#define SPECULAR_INTENSITYMAP_UV `+n.specularIntensityMapUv:``,n.transmissionMapUv?`#define TRANSMISSIONMAP_UV `+n.transmissionMapUv:``,n.thicknessMapUv?`#define THICKNESSMAP_UV `+n.thicknessMapUv:``,n.vertexTangents&&n.flatShading===!1?`#define USE_TANGENT`:``,n.vertexNormals?`#define HAS_NORMAL`:``,n.vertexColors?`#define USE_COLOR`:``,n.vertexAlphas?`#define USE_COLOR_ALPHA`:``,n.vertexUv1s?`#define USE_UV1`:``,n.vertexUv2s?`#define USE_UV2`:``,n.vertexUv3s?`#define USE_UV3`:``,n.pointsUvs?`#define USE_POINTS_UV`:``,n.flatShading?`#define FLAT_SHADED`:``,n.skinning?`#define USE_SKINNING`:``,n.morphTargets?`#define USE_MORPHTARGETS`:``,n.morphNormals&&n.flatShading===!1?`#define USE_MORPHNORMALS`:``,n.morphColors?`#define USE_MORPHCOLORS`:``,n.morphTargetsCount>0?`#define MORPHTARGETS_TEXTURE_STRIDE `+n.morphTextureStride:``,n.morphTargetsCount>0?`#define MORPHTARGETS_COUNT `+n.morphTargetsCount:``,n.doubleSided?`#define DOUBLE_SIDED`:``,n.flipSided?`#define FLIP_SIDED`:``,n.shadowMapEnabled?`#define USE_SHADOWMAP`:``,n.shadowMapEnabled?`#define `+c:``,n.sizeAttenuation?`#define USE_SIZEATTENUATION`:``,n.numLightProbes>0?`#define USE_LIGHT_PROBES`:``,n.logarithmicDepthBuffer?`#define USE_LOGARITHMIC_DEPTH_BUFFER`:``,n.reversedDepthBuffer?`#define USE_REVERSED_DEPTH_BUFFER`:``,`uniform mat4 modelMatrix;`,`uniform mat4 modelViewMatrix;`,`uniform mat4 projectionMatrix;`,`uniform mat4 viewMatrix;`,`uniform mat3 normalMatrix;`,`uniform vec3 cameraPosition;`,`uniform bool isOrthographic;`,`#ifdef USE_INSTANCING`,`	attribute mat4 instanceMatrix;`,`#endif`,`#ifdef USE_INSTANCING_COLOR`,`	attribute vec3 instanceColor;`,`#endif`,`#ifdef USE_INSTANCING_MORPH`,`	uniform sampler2D morphTexture;`,`#endif`,`attribute vec3 position;`,`attribute vec3 normal;`,`attribute vec2 uv;`,`#ifdef USE_UV1`,`	attribute vec2 uv1;`,`#endif`,`#ifdef USE_UV2`,`	attribute vec2 uv2;`,`#endif`,`#ifdef USE_UV3`,`	attribute vec2 uv3;`,`#endif`,`#ifdef USE_TANGENT`,`	attribute vec4 tangent;`,`#endif`,`#if defined( USE_COLOR_ALPHA )`,`	attribute vec4 color;`,`#elif defined( USE_COLOR )`,`	attribute vec3 color;`,`#endif`,`#ifdef USE_SKINNING`,`	attribute vec4 skinIndex;`,`	attribute vec4 skinWeight;`,`#endif`,`
`].filter(Im).join(`
`),_=[Km(n),`#define SHADER_TYPE `+n.shaderType,`#define SHADER_NAME `+n.shaderName,m,n.useFog&&n.fog?`#define USE_FOG`:``,n.useFog&&n.fogExp2?`#define FOG_EXP2`:``,n.alphaToCoverage?`#define ALPHA_TO_COVERAGE`:``,n.map?`#define USE_MAP`:``,n.matcap?`#define USE_MATCAP`:``,n.envMap?`#define USE_ENVMAP`:``,n.envMap?`#define `+l:``,n.envMap?`#define `+u:``,n.envMap?`#define `+d:``,f?`#define CUBEUV_TEXEL_WIDTH `+f.texelWidth:``,f?`#define CUBEUV_TEXEL_HEIGHT `+f.texelHeight:``,f?`#define CUBEUV_MAX_MIP `+f.maxMip+`.0`:``,n.lightMap?`#define USE_LIGHTMAP`:``,n.aoMap?`#define USE_AOMAP`:``,n.bumpMap?`#define USE_BUMPMAP`:``,n.normalMap?`#define USE_NORMALMAP`:``,n.normalMapObjectSpace?`#define USE_NORMALMAP_OBJECTSPACE`:``,n.normalMapTangentSpace?`#define USE_NORMALMAP_TANGENTSPACE`:``,n.packedNormalMap?`#define USE_PACKED_NORMALMAP`:``,n.emissiveMap?`#define USE_EMISSIVEMAP`:``,n.anisotropy?`#define USE_ANISOTROPY`:``,n.anisotropyMap?`#define USE_ANISOTROPYMAP`:``,n.clearcoat?`#define USE_CLEARCOAT`:``,n.clearcoatMap?`#define USE_CLEARCOATMAP`:``,n.clearcoatRoughnessMap?`#define USE_CLEARCOAT_ROUGHNESSMAP`:``,n.clearcoatNormalMap?`#define USE_CLEARCOAT_NORMALMAP`:``,n.dispersion?`#define USE_DISPERSION`:``,n.retroreflection?`#define USE_RETROREFLECTION`:``,n.iridescence?`#define USE_IRIDESCENCE`:``,n.iridescenceMap?`#define USE_IRIDESCENCEMAP`:``,n.iridescenceThicknessMap?`#define USE_IRIDESCENCE_THICKNESSMAP`:``,n.specularMap?`#define USE_SPECULARMAP`:``,n.specularColorMap?`#define USE_SPECULAR_COLORMAP`:``,n.specularIntensityMap?`#define USE_SPECULAR_INTENSITYMAP`:``,n.roughnessMap?`#define USE_ROUGHNESSMAP`:``,n.metalnessMap?`#define USE_METALNESSMAP`:``,n.alphaMap?`#define USE_ALPHAMAP`:``,n.alphaTest?`#define USE_ALPHATEST`:``,n.alphaHash?`#define USE_ALPHAHASH`:``,n.sheen?`#define USE_SHEEN`:``,n.sheenColorMap?`#define USE_SHEEN_COLORMAP`:``,n.sheenRoughnessMap?`#define USE_SHEEN_ROUGHNESSMAP`:``,n.transmission?`#define USE_TRANSMISSION`:``,n.transmissionMap?`#define USE_TRANSMISSIONMAP`:``,n.thicknessMap?`#define USE_THICKNESSMAP`:``,n.vertexTangents&&n.flatShading===!1?`#define USE_TANGENT`:``,n.vertexColors||n.instancingColor?`#define USE_COLOR`:``,n.vertexAlphas||n.batchingColor?`#define USE_COLOR_ALPHA`:``,n.vertexUv1s?`#define USE_UV1`:``,n.vertexUv2s?`#define USE_UV2`:``,n.vertexUv3s?`#define USE_UV3`:``,n.pointsUvs?`#define USE_POINTS_UV`:``,n.gradientMap?`#define USE_GRADIENTMAP`:``,n.flatShading?`#define FLAT_SHADED`:``,n.doubleSided?`#define DOUBLE_SIDED`:``,n.flipSided?`#define FLIP_SIDED`:``,n.shadowMapEnabled?`#define USE_SHADOWMAP`:``,n.shadowMapEnabled?`#define `+c:``,n.premultipliedAlpha?`#define PREMULTIPLIED_ALPHA`:``,n.numLightProbes>0?`#define USE_LIGHT_PROBES`:``,n.numLightProbeGrids>0?`#define USE_LIGHT_PROBES_GRID`:``,n.decodeVideoTexture?`#define DECODE_VIDEO_TEXTURE`:``,n.decodeVideoTextureEmissive?`#define DECODE_VIDEO_TEXTURE_EMISSIVE`:``,n.logarithmicDepthBuffer?`#define USE_LOGARITHMIC_DEPTH_BUFFER`:``,n.reversedDepthBuffer?`#define USE_REVERSED_DEPTH_BUFFER`:``,`uniform mat4 viewMatrix;`,`uniform vec3 cameraPosition;`,`uniform bool isOrthographic;`,n.toneMapping===0?``:`#define TONE_MAPPING`,n.toneMapping===0?``:Df.tonemapping_pars_fragment,n.toneMapping===0?``:Am(`toneMapping`,n.toneMapping),n.dithering?`#define DITHERING`:``,n.opaque?`#define OPAQUE`:``,Df.colorspace_pars_fragment,Om(`linearToOutputTexel`,n.outputColorSpace),Mm(),n.useDepthPacking?`#define DEPTH_PACKING `+n.depthPacking:``,`
`].filter(Im).join(`
`)),o=Bm(o),o=Lm(o,n),o=Rm(o,n),s=Bm(s),s=Lm(s,n),s=Rm(s,n),o=Wm(o),s=Wm(s),n.isRawShaderMaterial!==!0&&(v=`#version 300 es
`,g=[p,`#define attribute in`,`#define varying out`,`#define texture2D texture`].join(`
`)+`
`+g,_=[`#define varying in`,n.glslVersion===`300 es`?``:`layout(location = 0) out highp vec4 pc_fragColor;`,n.glslVersion===`300 es`?``:`#define gl_FragColor pc_fragColor`,`#define gl_FragDepthEXT gl_FragDepth`,`#define texture2D texture`,`#define textureCube texture`,`#define texture2DProj textureProj`,`#define texture2DLodEXT textureLod`,`#define texture2DProjLodEXT textureProjLod`,`#define textureCubeLodEXT textureLod`,`#define texture2DGradEXT textureGrad`,`#define texture2DProjGradEXT textureProjGrad`,`#define textureCubeGradEXT textureGrad`].join(`
`)+`
`+_);let y=v+g+o,b=v+_+s,x=xm(i,i.VERTEX_SHADER,y),S=xm(i,i.FRAGMENT_SHADER,b);i.attachShader(h,x),i.attachShader(h,S),n.index0AttributeName===void 0?n.hasPositionAttribute===!0&&i.bindAttribLocation(h,0,`position`):i.bindAttribLocation(h,0,n.index0AttributeName),i.linkProgram(h);function C(t){if(e.debug.checkShaderErrors){let n=i.getProgramInfoLog(h)||``,r=i.getShaderInfoLog(x)||``,a=i.getShaderInfoLog(S)||``,o=n.trim(),s=r.trim(),c=a.trim(),l=!0,u=!0;if(i.getProgramParameter(h,i.LINK_STATUS)===!1){if(l=!1,typeof e.debug.onShaderError==`function`)e.debug.onShaderError(i,h,x,S);else{let e=Dm(i,x,`vertex`),n=Dm(i,S,`fragment`);q(`WebGLProgram: Shader Error `+i.getError()+` - VALIDATE_STATUS `+i.getProgramParameter(h,i.VALIDATE_STATUS)+`

Material Name: `+t.name+`
Material Type: `+t.type+`

Program Info Log: `+o+`
`+e+`
`+n)}}else o===``?(s===``||c===``)&&(u=!1):K(`WebGLProgram: Program Info Log:`,o);u&&(t.diagnostics={runnable:l,programLog:o,vertexShader:{log:s,prefix:g},fragmentShader:{log:c,prefix:_}})}i.deleteShader(x),i.deleteShader(S),w=new bm(i,h),T=Fm(i,h)}let w;this.getUniforms=function(){return w===void 0&&C(this),w};let T;this.getAttributes=function(){return T===void 0&&C(this),T};let E=n.rendererExtensionParallelShaderCompile===!1;return this.isReady=function(){return E===!1&&(E=i.getProgramParameter(h,Sm)),E},this.destroy=function(){r.releaseStatesOfProgram(this),i.deleteProgram(h),this.program=void 0},this.type=n.shaderType,this.name=n.shaderName,this.id=Cm++,this.cacheKey=t,this.usedTimes=1,this.program=h,this.vertexShader=x,this.fragmentShader=S,this}var rh=0,ih=class{constructor(){this.shaderCache=new Map,this.materialCache=new Map}update(e,t,n){let r=this._getShaderCacheForMaterial(e);return r.has(t)===!1&&(r.add(t),t.usedTimes++),r.has(n)===!1&&(r.add(n),n.usedTimes++),this}remove(e){let t=this.materialCache.get(e);for(let e of t)e.usedTimes--,e.usedTimes===0&&this.shaderCache.delete(e.code);return this.materialCache.delete(e),this}getVertexShaderStage(e){return this._getShaderStage(e.vertexShader)}getFragmentShaderStage(e){return this._getShaderStage(e.fragmentShader)}dispose(){this.shaderCache.clear(),this.materialCache.clear()}_getShaderCacheForMaterial(e){let t=this.materialCache,n=t.get(e);return n===void 0&&(n=new Set,t.set(e,n)),n}_getShaderStage(e){let t=this.shaderCache,n=t.get(e);return n===void 0&&(n=new ah(e),t.set(e,n)),n}},ah=class{constructor(e){this.id=rh++,this.code=e,this.usedTimes=0}};function oh(e){return e===1030||e===37490||e===36285}function sh(e,t,n,r,i,a){let o=new Gs,s=new ih,c=new Set,l=[],u=new Map,d=r.logarithmicDepthBuffer,f=r.precision,p={MeshDepthMaterial:`depth`,MeshDistanceMaterial:`distance`,MeshNormalMaterial:`normal`,MeshBasicMaterial:`basic`,MeshLambertMaterial:`lambert`,MeshPhongMaterial:`phong`,MeshToonMaterial:`toon`,MeshStandardMaterial:`physical`,MeshPhysicalMaterial:`physical`,MeshMatcapMaterial:`matcap`,LineBasicMaterial:`basic`,LineDashedMaterial:`dashed`,PointsMaterial:`points`,ShadowMaterial:`shadow`,SpriteMaterial:`sprite`};function m(e){return c.add(e),e===0?`uv`:`uv${e}`}function h(i,o,l,u,h,g){let _=u.fog,v=h.geometry,y=i.isMeshStandardMaterial||i.isMeshLambertMaterial||i.isMeshPhongMaterial?u.environment:null,b=i.isMeshStandardMaterial||i.isMeshLambertMaterial&&!i.envMap||i.isMeshPhongMaterial&&!i.envMap,x=t.get(i.envMap||y,b),S=x&&x.mapping===306?x.image.height:null,C=p[i.type];i.precision!==null&&(f=r.getMaxPrecision(i.precision),f!==i.precision&&K(`WebGLProgram.getParameters:`,i.precision,`not supported, using`,f,`instead.`));let w=v.morphAttributes.position||v.morphAttributes.normal||v.morphAttributes.color,T=w===void 0?0:w.length,E=0;v.morphAttributes.position!==void 0&&(E=1),v.morphAttributes.normal!==void 0&&(E=2),v.morphAttributes.color!==void 0&&(E=3);let D,O,k,A;if(C){let e=Of[C];D=e.vertexShader,O=e.fragmentShader}else{D=i.vertexShader,O=i.fragmentShader;let e=s.getVertexShaderStage(i),t=s.getFragmentShaderStage(i);s.update(i,e,t),k=e.id,A=t.id}let j=e.getRenderTarget(),M=e.state.buffers.depth.getReversed(),N=h.isInstancedMesh===!0,P=h.isBatchedMesh===!0,F=!!i.map,ee=!!i.matcap,te=!!x,I=!!i.aoMap,L=!!i.lightMap,ne=!!i.bumpMap&&i.wireframe===!1,re=!!i.normalMap,ie=!!i.displacementMap,ae=!!i.emissiveMap,oe=!!i.metalnessMap,se=!!i.roughnessMap,ce=i.anisotropy>0,le=i.clearcoat>0,ue=i.dispersion>0,de=i.retroreflectivity>0,fe=i.iridescence>0,pe=i.sheen>0,me=i.transmission>0,he=ce&&!!i.anisotropyMap,ge=le&&!!i.clearcoatMap,_e=le&&!!i.clearcoatNormalMap,ve=le&&!!i.clearcoatRoughnessMap,ye=fe&&!!i.iridescenceMap,R=fe&&!!i.iridescenceThicknessMap,be=pe&&!!i.sheenColorMap,xe=pe&&!!i.sheenRoughnessMap,Se=!!i.specularMap,z=!!i.specularColorMap,Ce=!!i.specularIntensityMap,B=me&&!!i.transmissionMap,V=me&&!!i.thicknessMap,we=!!i.gradientMap,Te=!!i.alphaMap,Ee=i.alphaTest>0,De=!!i.alphaHash,Oe=!!i.extensions,ke=0;i.toneMapped&&(j===null||j.isXRRenderTarget===!0)&&(ke=e.toneMapping);let Ae={shaderID:C,shaderType:i.type,shaderName:i.name,vertexShader:D,fragmentShader:O,defines:i.defines,customVertexShaderID:k,customFragmentShaderID:A,isRawShaderMaterial:i.isRawShaderMaterial===!0,glslVersion:i.glslVersion,precision:f,batching:P,batchingColor:P&&h._colorsTexture!==null,instancing:N,instancingColor:N&&h.instanceColor!==null,instancingMorph:N&&h.morphTexture!==null,outputColorSpace:j===null?e.outputColorSpace:j.isXRRenderTarget===!0?j.texture.colorSpace:vs.workingColorSpace,alphaToCoverage:!!i.alphaToCoverage,map:F,matcap:ee,envMap:te,envMapMode:te&&x.mapping,envMapCubeUVHeight:S,aoMap:I,lightMap:L,bumpMap:ne,normalMap:re,displacementMap:ie,emissiveMap:ae,normalMapObjectSpace:re&&i.normalMapType===1,normalMapTangentSpace:re&&i.normalMapType===0,packedNormalMap:re&&i.normalMapType===0&&oh(i.normalMap.format),metalnessMap:oe,roughnessMap:se,anisotropy:ce,anisotropyMap:he,clearcoat:le,clearcoatMap:ge,clearcoatNormalMap:_e,clearcoatRoughnessMap:ve,dispersion:ue,retroreflection:de,iridescence:fe,iridescenceMap:ye,iridescenceThicknessMap:R,sheen:pe,sheenColorMap:be,sheenRoughnessMap:xe,specularMap:Se,specularColorMap:z,specularIntensityMap:Ce,transmission:me,transmissionMap:B,thicknessMap:V,gradientMap:we,opaque:i.transparent===!1&&i.blending===1&&i.alphaToCoverage===!1,alphaMap:Te,alphaTest:Ee,alphaHash:De,combine:i.combine,mapUv:F&&m(i.map.channel),aoMapUv:I&&m(i.aoMap.channel),lightMapUv:L&&m(i.lightMap.channel),bumpMapUv:ne&&m(i.bumpMap.channel),normalMapUv:re&&m(i.normalMap.channel),displacementMapUv:ie&&m(i.displacementMap.channel),emissiveMapUv:ae&&m(i.emissiveMap.channel),metalnessMapUv:oe&&m(i.metalnessMap.channel),roughnessMapUv:se&&m(i.roughnessMap.channel),anisotropyMapUv:he&&m(i.anisotropyMap.channel),clearcoatMapUv:ge&&m(i.clearcoatMap.channel),clearcoatNormalMapUv:_e&&m(i.clearcoatNormalMap.channel),clearcoatRoughnessMapUv:ve&&m(i.clearcoatRoughnessMap.channel),iridescenceMapUv:ye&&m(i.iridescenceMap.channel),iridescenceThicknessMapUv:R&&m(i.iridescenceThicknessMap.channel),sheenColorMapUv:be&&m(i.sheenColorMap.channel),sheenRoughnessMapUv:xe&&m(i.sheenRoughnessMap.channel),specularMapUv:Se&&m(i.specularMap.channel),specularColorMapUv:z&&m(i.specularColorMap.channel),specularIntensityMapUv:Ce&&m(i.specularIntensityMap.channel),transmissionMapUv:B&&m(i.transmissionMap.channel),thicknessMapUv:V&&m(i.thicknessMap.channel),alphaMapUv:Te&&m(i.alphaMap.channel),vertexTangents:!!v.attributes.tangent&&(re||ce),vertexNormals:!!v.attributes.normal,vertexColors:i.vertexColors,vertexAlphas:i.vertexColors===!0&&!!v.attributes.color&&v.attributes.color.itemSize===4,pointsUvs:h.isPoints===!0&&!!v.attributes.uv&&(F||Te),fog:!!_,useFog:i.fog===!0,fogExp2:!!_&&_.isFogExp2,flatShading:i.wireframe===!1&&(i.flatShading===!0||v.attributes.normal===void 0&&re===!1&&(i.isMeshLambertMaterial||i.isMeshPhongMaterial||i.isMeshStandardMaterial||i.isMeshPhysicalMaterial)),sizeAttenuation:i.sizeAttenuation===!0,logarithmicDepthBuffer:d,reversedDepthBuffer:M,skinning:h.isSkinnedMesh===!0,hasPositionAttribute:v.attributes.position!==void 0,morphTargets:v.morphAttributes.position!==void 0,morphNormals:v.morphAttributes.normal!==void 0,morphColors:v.morphAttributes.color!==void 0,morphTargetsCount:T,morphTextureStride:E,numSunLights:o.sun.length,numDirLights:o.directional.length,numPointLights:o.point.length,numSpotLights:o.spot.length,numSpotLightMaps:o.spotLightMap.length,numRectAreaLights:o.rectArea.length,numHemiLights:o.hemi.length,numSunLightShadows:o.sunShadowMap.length,numDirLightShadows:o.directionalShadowMap.length,numPointLightShadows:o.pointShadowMap.length,numSpotLightShadows:o.spotShadowMap.length,numSpotLightShadowsWithMaps:o.numSpotLightShadowsWithMaps,numLightProbes:o.numLightProbes,numLightProbeGrids:g.length,numClippingPlanes:a.numPlanes,numClipIntersection:a.numIntersection,dithering:i.dithering,shadowMapEnabled:e.shadowMap.enabled&&l.length>0,shadowMapType:e.shadowMap.type,toneMapping:ke,decodeVideoTexture:F&&i.map.isVideoTexture===!0&&vs.getTransfer(i.map.colorSpace)===`srgb`,decodeVideoTextureEmissive:ae&&i.emissiveMap.isVideoTexture===!0&&vs.getTransfer(i.emissiveMap.colorSpace)===`srgb`,premultipliedAlpha:i.premultipliedAlpha,doubleSided:i.side===2,flipSided:i.side===1,useDepthPacking:i.depthPacking>=0,depthPacking:i.depthPacking||0,index0AttributeName:i.index0AttributeName,extensionClipCullDistance:Oe&&i.extensions.clipCullDistance===!0&&n.has(`WEBGL_clip_cull_distance`),extensionMultiDraw:(Oe&&i.extensions.multiDraw===!0||P)&&n.has(`WEBGL_multi_draw`),rendererExtensionParallelShaderCompile:n.has(`KHR_parallel_shader_compile`),customProgramCacheKey:i.customProgramCacheKey()};return Ae.vertexUv1s=c.has(1),Ae.vertexUv2s=c.has(2),Ae.vertexUv3s=c.has(3),c.clear(),Ae}function g(t){let n=[];if(t.shaderID?n.push(t.shaderID):(n.push(t.customVertexShaderID),n.push(t.customFragmentShaderID)),t.defines!==void 0)for(let e in t.defines)n.push(e),n.push(t.defines[e]);return t.isRawShaderMaterial===!1&&(_(n,t),v(n,t),n.push(e.outputColorSpace)),n.push(t.customProgramCacheKey),n.join()}function _(e,t){e.push(t.precision),e.push(t.outputColorSpace),e.push(t.envMapMode),e.push(t.envMapCubeUVHeight),e.push(t.mapUv),e.push(t.alphaMapUv),e.push(t.lightMapUv),e.push(t.aoMapUv),e.push(t.bumpMapUv),e.push(t.normalMapUv),e.push(t.displacementMapUv),e.push(t.emissiveMapUv),e.push(t.metalnessMapUv),e.push(t.roughnessMapUv),e.push(t.anisotropyMapUv),e.push(t.clearcoatMapUv),e.push(t.clearcoatNormalMapUv),e.push(t.clearcoatRoughnessMapUv),e.push(t.iridescenceMapUv),e.push(t.iridescenceThicknessMapUv),e.push(t.sheenColorMapUv),e.push(t.sheenRoughnessMapUv),e.push(t.specularMapUv),e.push(t.specularColorMapUv),e.push(t.specularIntensityMapUv),e.push(t.transmissionMapUv),e.push(t.thicknessMapUv),e.push(t.combine),e.push(t.fogExp2),e.push(t.sizeAttenuation),e.push(t.morphTargetsCount),e.push(t.morphAttributeCount),e.push(t.numSunLights),e.push(t.numDirLights),e.push(t.numPointLights),e.push(t.numSpotLights),e.push(t.numSpotLightMaps),e.push(t.numHemiLights),e.push(t.numRectAreaLights),e.push(t.numSunLightShadows),e.push(t.numDirLightShadows),e.push(t.numPointLightShadows),e.push(t.numSpotLightShadows),e.push(t.numSpotLightShadowsWithMaps),e.push(t.numLightProbes),e.push(t.shadowMapType),e.push(t.toneMapping),e.push(t.numClippingPlanes),e.push(t.numClipIntersection),e.push(t.depthPacking)}function v(e,t){o.disableAll(),t.instancing&&o.enable(0),t.instancingColor&&o.enable(1),t.instancingMorph&&o.enable(2),t.matcap&&o.enable(3),t.envMap&&o.enable(4),t.normalMapObjectSpace&&o.enable(5),t.normalMapTangentSpace&&o.enable(6),t.clearcoat&&o.enable(7),t.iridescence&&o.enable(8),t.alphaTest&&o.enable(9),t.vertexColors&&o.enable(10),t.vertexAlphas&&o.enable(11),t.vertexUv1s&&o.enable(12),t.vertexUv2s&&o.enable(13),t.vertexUv3s&&o.enable(14),t.vertexTangents&&o.enable(15),t.anisotropy&&o.enable(16),t.alphaHash&&o.enable(17),t.batching&&o.enable(18),t.dispersion&&o.enable(19),t.retroreflection&&o.enable(24),t.batchingColor&&o.enable(20),t.gradientMap&&o.enable(21),t.packedNormalMap&&o.enable(22),t.vertexNormals&&o.enable(23),e.push(o.mask),o.disableAll(),t.fog&&o.enable(0),t.useFog&&o.enable(1),t.flatShading&&o.enable(2),t.logarithmicDepthBuffer&&o.enable(3),t.reversedDepthBuffer&&o.enable(4),t.skinning&&o.enable(5),t.morphTargets&&o.enable(6),t.morphNormals&&o.enable(7),t.morphColors&&o.enable(8),t.premultipliedAlpha&&o.enable(9),t.shadowMapEnabled&&o.enable(10),t.doubleSided&&o.enable(11),t.flipSided&&o.enable(12),t.useDepthPacking&&o.enable(13),t.dithering&&o.enable(14),t.transmission&&o.enable(15),t.sheen&&o.enable(16),t.opaque&&o.enable(17),t.pointsUvs&&o.enable(18),t.decodeVideoTexture&&o.enable(19),t.decodeVideoTextureEmissive&&o.enable(20),t.alphaToCoverage&&o.enable(21),t.numLightProbeGrids>0&&o.enable(22),t.hasPositionAttribute&&o.enable(23),e.push(o.mask)}function y(e){let t=p[e.type],n;if(t){let e=Of[t];n=ed.clone(e.uniforms)}else n=e.uniforms;return n}function b(t,n){let r=u.get(n);return r===void 0?(r=new nh(e,n,t,i),l.push(r),u.set(n,r)):++r.usedTimes,r}function x(e){if(--e.usedTimes===0){let t=l.indexOf(e);l[t]=l[l.length-1],l.pop(),u.delete(e.cacheKey),e.destroy()}}function S(e){s.remove(e)}function C(){s.dispose()}return{getParameters:h,getProgramCacheKey:g,getUniforms:y,acquireProgram:b,releaseProgram:x,releaseShaderCache:S,programs:l,dispose:C}}function ch(){let e=new WeakMap;function t(t){return e.has(t)}function n(t){let n=e.get(t);return n===void 0&&(n={},e.set(t,n)),n}function r(t){e.delete(t)}function i(t,n,r){e.get(t)[n]=r}function a(){e=new WeakMap}return{has:t,get:n,remove:r,update:i,dispose:a}}function lh(e,t){return e.groupOrder===t.groupOrder?e.renderOrder===t.renderOrder?e.material.id===t.material.id?e.materialVariant===t.materialVariant?e.z===t.z?e.id-t.id:e.z-t.z:e.materialVariant-t.materialVariant:e.material.id-t.material.id:e.renderOrder-t.renderOrder:e.groupOrder-t.groupOrder}function uh(e,t){return e.groupOrder===t.groupOrder?e.renderOrder===t.renderOrder?e.z===t.z?e.id-t.id:t.z-e.z:e.renderOrder-t.renderOrder:e.groupOrder-t.groupOrder}function dh(){let e=[],t=0,n=[],r=[],i=[];function a(){t=0,n.length=0,r.length=0,i.length=0}function o(e){let t=0;return e.isInstancedMesh&&(t+=2),e.isSkinnedMesh&&(t+=1),t}function s(n,r,i,a,s,c){let l=e[t];return l===void 0?(l={id:n.id,object:n,geometry:r,material:i,materialVariant:o(n),groupOrder:a,renderOrder:n.renderOrder,z:s,group:c},e[t]=l):(l.id=n.id,l.object=n,l.geometry=r,l.material=i,l.materialVariant=o(n),l.groupOrder=a,l.renderOrder=n.renderOrder,l.z=s,l.group=c),t++,l}function c(e,t,a,o,c,l,u){u.reversedDepth===!0&&(c=-c);let d=s(e,t,a,o,c,l);a.transmission>0?r.push(d):a.transparent===!0?i.push(d):n.push(d)}function l(e,t,a,o,c,l){let u=s(e,t,a,o,c,l);a.transmission>0?r.unshift(u):a.transparent===!0?i.unshift(u):n.unshift(u)}function u(e,t){n.length>1&&n.sort(e||lh),r.length>1&&r.sort(t||uh),i.length>1&&i.sort(t||uh)}function d(){for(let n=t,r=e.length;n<r;n++){let t=e[n];if(t.id===null)break;t.id=null,t.object=null,t.geometry=null,t.material=null,t.group=null}}return{opaque:n,transmissive:r,transparent:i,init:a,push:c,unshift:l,finish:d,sort:u}}function fh(){let e=new WeakMap;function t(t,n){let r=e.get(t),i;return r===void 0?(i=new dh,e.set(t,[i])):n>=r.length?(i=new dh,r.push(i)):i=r[n],i}function n(){e=new WeakMap}return{get:t,dispose:n}}function ph(){let e={};return{get:function(t){if(e[t.id]!==void 0)return e[t.id];let n;switch(t.type){case`SunLight`:case`DirectionalLight`:n={direction:new X,color:new mc};break;case`SpotLight`:n={position:new X,direction:new X,color:new mc,distance:0,coneCos:0,penumbraCos:0,decay:0};break;case`PointLight`:n={position:new X,color:new mc,distance:0,decay:0};break;case`HemisphereLight`:n={direction:new X,skyColor:new mc,groundColor:new mc};break;case`RectAreaLight`:n={color:new mc,position:new X,halfWidth:new X,halfHeight:new X}}return e[t.id]=n,n}}}function mh(){let e={};return{get:function(t){if(e[t.id]!==void 0)return e[t.id];let n;switch(t.type){case`SunLight`:case`DirectionalLight`:n={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Y};break;case`SpotLight`:n={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Y};break;case`PointLight`:n={shadowIntensity:1,shadowBias:0,shadowNormalBias:0,shadowRadius:1,shadowMapSize:new Y,shadowCameraNear:1,shadowCameraFar:1e3}}return e[t.id]=n,n}}}var hh=0;function gh(e,t){return(t.castShadow?2:0)-(e.castShadow?2:0)+ +!!t.map-!!e.map}function _h(e){let t=new ph,n=mh(),r={version:0,hash:{sunLength:-1,directionalLength:-1,pointLength:-1,spotLength:-1,rectAreaLength:-1,hemiLength:-1,numSunShadows:-1,numDirectionalShadows:-1,numPointShadows:-1,numSpotShadows:-1,numSpotMaps:-1,numLightProbes:-1},ambient:[0,0,0],probe:[],sun:[],sunShadow:[],sunShadowMap:[],sunShadowMatrix:[],sunShadowCascade:[],directional:[],directionalShadow:[],directionalShadowMap:[],directionalShadowMatrix:[],spot:[],spotLightMap:[],spotShadow:[],spotShadowMap:[],spotLightMatrix:[],rectArea:[],rectAreaLTC1:null,rectAreaLTC2:null,point:[],pointShadow:[],pointShadowMap:[],pointShadowMatrix:[],hemi:[],numSpotLightShadowsWithMaps:0,numLightProbes:0};for(let e=0;e<9;e++)r.probe.push(new X);let i=new X,a=new Ps,o=new Ps;function s(i){let a=0,o=0,s=0;for(let e=0;e<9;e++)r.probe[e].set(0,0,0);let c=0,l=0,u=0,d=0,f=0,p=0,m=0,h=0,g=0,_=0,v=0,y=0,b=0,x=0;i.sort(gh);for(let e=0,S=i.length;e<S;e++){let S=i[e],C=S.color,w=S.intensity,T=S.distance,E=null;if(S.shadow&&S.shadow.map&&(E=S.shadow.map.texture.format===1030?S.shadow.map.texture:S.shadow.map.depthTexture||S.shadow.map.texture),S.isAmbientLight)a+=C.r*w,o+=C.g*w,s+=C.b*w;else if(S.isLightProbe){for(let e=0;e<9;e++)r.probe[e].addScaledVector(S.sh.coefficients[e],w);x++}else if(S.isSunLight){let e=t.get(S);if(e.color.copy(S.color).multiplyScalar(S.intensity),S.castShadow){let e=S.shadow,t=n.get(S);t.shadowIntensity=e.intensity,t.shadowBias=e.bias,t.shadowNormalBias=e.normalBias,t.shadowRadius=e.radius,t.shadowMapSize.copy(e.mapSize).multiply(e.getFrameExtents()),r.sunShadow[l]=t,r.sunShadowMap[l]=E;let i=e.getViewportCount();for(let t=0;t<i;t++)r.sunShadowMatrix[u+t]=e.getMatrix(t),r.sunShadowCascade[u+t]=e._cascadeData[t];u+=i,l++}r.sun[c]=e,c++}else if(S.isDirectionalLight){let e=t.get(S);if(e.color.copy(S.color).multiplyScalar(S.intensity),S.castShadow){let e=S.shadow,t=n.get(S);t.shadowIntensity=e.intensity,t.shadowBias=e.bias,t.shadowNormalBias=e.normalBias,t.shadowRadius=e.radius,t.shadowMapSize=e.mapSize,r.directionalShadow[d]=t,r.directionalShadowMap[d]=E,r.directionalShadowMatrix[d]=S.shadow.matrix,g++}r.directional[d]=e,d++}else if(S.isSpotLight){let e=t.get(S);e.position.setFromMatrixPosition(S.matrixWorld),e.color.copy(C).multiplyScalar(w),e.distance=T,e.coneCos=Math.cos(S.angle),e.penumbraCos=Math.cos(S.angle*(1-S.penumbra)),e.decay=S.decay,r.spot[p]=e;let i=S.shadow;if(S.map&&(r.spotLightMap[y]=S.map,y++,i.updateMatrices(S),S.castShadow&&b++),r.spotLightMatrix[p]=i.matrix,S.castShadow){let e=n.get(S);e.shadowIntensity=i.intensity,e.shadowBias=i.bias,e.shadowNormalBias=i.normalBias,e.shadowRadius=i.radius,e.shadowMapSize=i.mapSize,r.spotShadow[p]=e,r.spotShadowMap[p]=E,v++}p++}else if(S.isRectAreaLight){let e=t.get(S);e.color.copy(C).multiplyScalar(w),e.halfWidth.set(S.width*.5,0,0),e.halfHeight.set(0,S.height*.5,0),r.rectArea[m]=e,m++}else if(S.isPointLight){let e=t.get(S);if(e.color.copy(S.color).multiplyScalar(S.intensity),e.distance=S.distance,e.decay=S.decay,S.castShadow){let e=S.shadow,t=n.get(S);t.shadowIntensity=e.intensity,t.shadowBias=e.bias,t.shadowNormalBias=e.normalBias,t.shadowRadius=e.radius,t.shadowMapSize=e.mapSize,t.shadowCameraNear=e.camera.near,t.shadowCameraFar=e.camera.far,r.pointShadow[f]=t,r.pointShadowMap[f]=E,r.pointShadowMatrix[f]=S.shadow.matrix,_++}r.point[f]=e,f++}else if(S.isHemisphereLight){let e=t.get(S);e.skyColor.copy(S.color).multiplyScalar(w),e.groundColor.copy(S.groundColor).multiplyScalar(w),r.hemi[h]=e,h++}}m>0&&(e.has(`OES_texture_float_linear`)===!0?(r.rectAreaLTC1=$.LTC_FLOAT_1,r.rectAreaLTC2=$.LTC_FLOAT_2):(r.rectAreaLTC1=$.LTC_HALF_1,r.rectAreaLTC2=$.LTC_HALF_2)),r.ambient[0]=a,r.ambient[1]=o,r.ambient[2]=s;let S=r.hash;(S.sunLength!==c||S.directionalLength!==d||S.pointLength!==f||S.spotLength!==p||S.rectAreaLength!==m||S.hemiLength!==h||S.numSunShadows!==l||S.numDirectionalShadows!==g||S.numPointShadows!==_||S.numSpotShadows!==v||S.numSpotMaps!==y||S.numLightProbes!==x)&&(r.sun.length=c,r.directional.length=d,r.spot.length=p,r.rectArea.length=m,r.point.length=f,r.hemi.length=h,r.sunShadow.length=l,r.sunShadowMap.length=l,r.sunShadowMatrix.length=u,r.sunShadowCascade.length=u,r.directionalShadow.length=g,r.directionalShadowMap.length=g,r.directionalShadowMatrix.length=g,r.pointShadow.length=_,r.pointShadowMap.length=_,r.pointShadowMatrix.length=_,r.spotShadow.length=v,r.spotShadowMap.length=v,r.spotLightMatrix.length=v+y-b,r.spotLightMap.length=y,r.numSpotLightShadowsWithMaps=b,r.numLightProbes=x,S.sunLength=c,S.directionalLength=d,S.pointLength=f,S.spotLength=p,S.rectAreaLength=m,S.hemiLength=h,S.numSunShadows=l,S.numDirectionalShadows=g,S.numPointShadows=_,S.numSpotShadows=v,S.numSpotMaps=y,S.numLightProbes=x,r.version=hh++)}function c(e,t){let n=0,s=0,c=0,l=0,u=0,d=0,f=t.matrixWorldInverse;for(let t=0,p=e.length;t<p;t++){let p=e[t];if(p.isSunLight){let e=r.sun[n];e.direction.setFromMatrixPosition(p.matrixWorld),e.direction.transformDirection(f),n++}else if(p.isDirectionalLight){let e=r.directional[s];e.direction.setFromMatrixPosition(p.matrixWorld),i.setFromMatrixPosition(p.target.matrixWorld),e.direction.sub(i),e.direction.transformDirection(f),s++}else if(p.isSpotLight){let e=r.spot[l];e.position.setFromMatrixPosition(p.matrixWorld),e.position.applyMatrix4(f),e.direction.setFromMatrixPosition(p.matrixWorld),i.setFromMatrixPosition(p.target.matrixWorld),e.direction.sub(i),e.direction.transformDirection(f),l++}else if(p.isRectAreaLight){let e=r.rectArea[u];e.position.setFromMatrixPosition(p.matrixWorld),e.position.applyMatrix4(f),o.identity(),a.copy(p.matrixWorld),a.premultiply(f),o.extractRotation(a),e.halfWidth.set(p.width*.5,0,0),e.halfHeight.set(0,p.height*.5,0),e.halfWidth.applyMatrix4(o),e.halfHeight.applyMatrix4(o),u++}else if(p.isPointLight){let e=r.point[c];e.position.setFromMatrixPosition(p.matrixWorld),e.position.applyMatrix4(f),c++}else if(p.isHemisphereLight){let e=r.hemi[d];e.direction.setFromMatrixPosition(p.matrixWorld),e.direction.transformDirection(f),d++}}}return{setup:s,setupView:c,state:r}}function vh(e){let t=new _h(e),n=[],r=[],i=[];function a(e){d.camera=e,n.length=0,r.length=0,i.length=0}function o(e){n.push(e)}function s(e){r.push(e)}function c(e){i.push(e)}function l(){t.setup(n)}function u(e){t.setupView(n,e)}let d={lightsArray:n,shadowsArray:r,lightProbeGridArray:i,camera:null,lights:t,transmissionRenderTarget:{},textureUnits:0};return{init:a,state:d,setupLights:l,setupLightsView:u,pushLight:o,pushShadow:s,pushLightProbeGrid:c}}function yh(e){let t=new WeakMap;function n(n,r=0){let i=t.get(n),a;return i===void 0?(a=new vh(e),t.set(n,[a])):r>=i.length?(a=new vh(e),i.push(a)):a=i[r],a}function r(){t=new WeakMap}return{get:n,dispose:r}}var bh=`void main() {
	gl_Position = vec4( position, 1.0 );
}`,xh=`uniform sampler2D shadow_pass;
uniform vec2 resolution;
uniform float radius;
void main() {
	const float samples = float( VSM_SAMPLES );
	float mean = 0.0;
	float squared_mean = 0.0;
	float uvStride = samples <= 1.0 ? 0.0 : 2.0 / ( samples - 1.0 );
	float uvStart = samples <= 1.0 ? 0.0 : - 1.0;
	for ( float i = 0.0; i < samples; i ++ ) {
		float uvOffset = uvStart + i * uvStride;
		#ifdef HORIZONTAL_PASS
			vec2 distribution = texture2D( shadow_pass, ( gl_FragCoord.xy + vec2( uvOffset, 0.0 ) * radius ) / resolution ).rg;
			mean += distribution.x;
			squared_mean += distribution.y * distribution.y + distribution.x * distribution.x;
		#else
			float depth = texture2D( shadow_pass, ( gl_FragCoord.xy + vec2( 0.0, uvOffset ) * radius ) / resolution ).r;
			mean += depth;
			squared_mean += depth * depth;
		#endif
	}
	mean = mean / samples;
	squared_mean = squared_mean / samples;
	float std_dev = sqrt( max( 0.0, squared_mean - mean * mean ) );
	gl_FragColor = vec4( mean, std_dev, 0.0, 1.0 );
}`,Sh=[new X(1,0,0),new X(-1,0,0),new X(0,1,0),new X(0,-1,0),new X(0,0,1),new X(0,0,-1)],Ch=[new X(0,-1,0),new X(0,-1,0),new X(0,0,1),new X(0,0,-1),new X(0,-1,0),new X(0,-1,0)],wh=new Ps,Th=new X,Eh=new X;function Dh(e,t,n){let r=new Wl,i=new Y,a=new Y,o=new ks,s=new od,c=new sd,l={},u=n.maxTextureSize,d={0:1,1:0,2:2},f=new rd({defines:{VSM_SAMPLES:8},uniforms:{shadow_pass:{value:null},resolution:{value:new Y},radius:{value:4}},vertexShader:bh,fragmentShader:xh}),p=f.clone();p.defines.HORIZONTAL_PASS=1;let m=new ul;m.setAttribute(`position`,new Yc(new Float32Array([-1,-1,.5,3,-1,.5,-1,3,.5]),3));let h=new Ll(m,f),g=this;this.enabled=!1,this.autoUpdate=!0,this.needsUpdate=!1,this.type=1;let _=this.type;this.render=function(t,n,s){if(g.enabled===!1||g.autoUpdate===!1&&g.needsUpdate===!1||t.length===0)return;this.type===2&&(K(`WebGLShadowMap: PCFSoftShadowMap has been removed. Using PCFShadowMap instead.`),this.type=1);let c=e.getRenderTarget(),l=e.getActiveCubeFace(),d=e.getActiveMipmapLevel(),f=e.state;f.setBlending(0),f.buffers.depth.getReversed()===!0?f.buffers.color.setClear(0,0,0,0):f.buffers.color.setClear(1,1,1,1),f.buffers.depth.setTest(!0),f.setScissorTest(!1);let p=_!==this.type;p&&n.traverse(function(e){e.material&&(Array.isArray(e.material)?e.material.forEach(e=>e.needsUpdate=!0):e.material.needsUpdate=!0)});for(let c=0,l=t.length;c<l;c++){let l=t[c],d=l.shadow;if(d===void 0){K(`WebGLShadowMap:`,l,`has no shadow.`);continue}if(d.autoUpdate===!1&&d.needsUpdate===!1)continue;i.copy(d.mapSize);let m=d.getFrameExtents();i.multiply(m),a.copy(d.mapSize),(i.x>u||i.y>u)&&(i.x>u&&(a.x=Math.floor(u/m.x),i.x=a.x*m.x,d.mapSize.x=a.x),i.y>u&&(a.y=Math.floor(u/m.y),i.y=a.y*m.y,d.mapSize.y=a.y));let h=e.state.buffers.depth.getReversed();if(d.camera._reversedDepth=h,d.map===null||p===!0){if(d.map!==null&&(d.map.depthTexture!==null&&(d.map.depthTexture.dispose(),d.map.depthTexture=null),d.map.dispose()),this.type===3){if(l.isPointLight){K(`WebGLShadowMap: VSM shadow maps are not supported for PointLights. Use PCF or BasicShadowMap instead.`);continue}d.map=new js(i.x,i.y,{format:Da,type:ma,minFilter:ia,magFilter:ia,generateMipmaps:!1}),d.map.texture.name=l.name+`.shadowMap`,d.map.depthTexture=new pu(i.x,i.y,pa),d.map.depthTexture.name=l.name+`.shadowMapDepth`,d.map.depthTexture.format=Ca,d.map.depthTexture.compareFunction=null,d.map.depthTexture.minFilter=ta,d.map.depthTexture.magFilter=ta}else l.isPointLight?(d.map=new ip(i.x),d.map.depthTexture=new mu(i.x,fa)):(d.map=new js(i.x,i.y),d.map.depthTexture=new pu(i.x,i.y,fa)),d.map.depthTexture.name=l.name+`.shadowMap`,d.map.depthTexture.format=Ca,this.type===1?(d.map.depthTexture.compareFunction=h?518:515,d.map.depthTexture.minFilter=ia,d.map.depthTexture.magFilter=ia):(d.map.depthTexture.compareFunction=null,d.map.depthTexture.minFilter=ta,d.map.depthTexture.magFilter=ta);d.camera.updateProjectionMatrix()}d.map.isWebGLCubeRenderTarget!==!0&&(d.map.width!==i.x||d.map.height!==i.y)&&d.map.setSize(i.x,i.y);let g=d.map.isWebGLCubeRenderTarget?6:d.getViewportCount();l.isPointLight!==!0&&d.updateMatrices(l,s);for(let t=0;t<g;t++){let i=d.getCamera(t);if(l.isPointLight){let e=d.camera,n=d.matrix,r=l.distance||e.far;r!==e.far&&(e.far=r,e.updateProjectionMatrix()),Th.setFromMatrixPosition(l.matrixWorld),e.position.copy(Th),Eh.copy(e.position),Eh.add(Sh[t]),e.up.copy(Ch[t]),e.lookAt(Eh),e.updateMatrixWorld(),n.makeTranslation(-Th.x,-Th.y,-Th.z),wh.multiplyMatrices(e.projectionMatrix,e.matrixWorldInverse),d._frustum.setFromProjectionMatrix(wh,e.coordinateSystem,e.reversedDepth)}if(d.map.isWebGLCubeRenderTarget)e.setRenderTarget(d.map,t),e.clear();else{t===0&&(e.setRenderTarget(d.map),e.clear());let n=d.getViewport(t);o.set(a.x*n.x,a.y*n.y,a.x*n.z,a.y*n.w),f.viewport(o)}r=d.getFrustum(t),b(n,s,i,l,this.type)}d.isPointLightShadow!==!0&&this.type===3&&v(d,s),d.needsUpdate=!1}_=this.type,g.needsUpdate=!1,e.setRenderTarget(c,l,d)};function v(n,r){let a=t.update(h);f.defines.VSM_SAMPLES!==n.blurSamples&&(f.defines.VSM_SAMPLES=n.blurSamples,p.defines.VSM_SAMPLES=n.blurSamples,f.needsUpdate=!0,p.needsUpdate=!0),n.mapPass===null?n.mapPass=new js(i.x,i.y,{format:Da,type:ma}):(n.mapPass.width!==n.map.width||n.mapPass.height!==n.map.height)&&n.mapPass.setSize(n.map.width,n.map.height),f.uniforms.shadow_pass.value=n.map.depthTexture,f.uniforms.resolution.value.set(n.map.width,n.map.height),f.uniforms.radius.value=n.radius,e.setRenderTarget(n.mapPass),e.clear(),e.renderBufferDirect(r,null,a,f,h,null),p.uniforms.shadow_pass.value=n.mapPass.texture,p.uniforms.resolution.value.set(n.map.width,n.map.height),p.uniforms.radius.value=n.radius,e.setRenderTarget(n.map),e.clear(),e.renderBufferDirect(r,null,a,p,h,null)}function y(t,n,r,i){let a=null,o=r.isPointLight===!0?t.customDistanceMaterial:t.customDepthMaterial;if(o!==void 0)a=o;else if(a=r.isPointLight===!0?c:s,e.localClippingEnabled&&n.clipShadows===!0&&Array.isArray(n.clippingPlanes)&&n.clippingPlanes.length!==0||n.displacementMap&&n.displacementScale!==0||n.alphaMap&&n.alphaTest>0||n.map&&n.alphaTest>0||n.alphaToCoverage===!0){let e=a.uuid,t=n.uuid,r=l[e];r===void 0&&(r={},l[e]=r);let i=r[t];i===void 0&&(i=a.clone(),r[t]=i,n.addEventListener(`dispose`,x)),a=i}if(a.visible=n.visible,a.wireframe=n.wireframe,i===3?a.side=n.shadowSide===null?n.side:n.shadowSide:a.side=n.shadowSide===null?d[n.side]:n.shadowSide,a.alphaMap=n.alphaMap,a.alphaTest=n.alphaToCoverage===!0?.5:n.alphaTest,a.map=n.map,a.clipShadows=n.clipShadows,a.clippingPlanes=n.clippingPlanes,a.clipIntersection=n.clipIntersection,a.displacementMap=n.displacementMap,a.displacementScale=n.displacementScale,a.displacementBias=n.displacementBias,a.wireframeLinewidth=n.wireframeLinewidth,a.linewidth=n.linewidth,r.isPointLight===!0&&a.isMeshDistanceMaterial===!0){let t=e.properties.get(a);t.light=r}return a}function b(n,i,a,o,s){if(n.visible===!1)return;if(n.layers.test(i.layers)&&(n.isMesh||n.isLine||n.isPoints)&&(n.castShadow||n.receiveShadow&&s===3)&&(!n.frustumCulled||n.intersectsFrustum(r))){n.modelViewMatrix.multiplyMatrices(a.matrixWorldInverse,n.matrixWorld);let r=t.update(n),c=n.material;if(Array.isArray(c)){let t=r.groups;for(let l=0,u=t.length;l<u;l++){let u=t[l],d=c[u.materialIndex];if(d&&d.visible){let t=y(n,d,o,s);n.onBeforeShadow(e,n,i,a,r,t,u),e.renderBufferDirect(a,null,r,t,n,u),n.onAfterShadow(e,n,i,a,r,t,u)}}}else if(c.visible){let t=y(n,c,o,s);n.onBeforeShadow(e,n,i,a,r,t,null),e.renderBufferDirect(a,null,r,t,n,null),n.onAfterShadow(e,n,i,a,r,t,null)}}let c=n.children;for(let e=0,t=c.length;e<t;e++)b(c[e],i,a,o,s)}function x(e){e.target.removeEventListener(`dispose`,x);for(let t in l){let n=l[t],r=e.target.uuid;r in n&&(n[r].dispose(),delete n[r])}}}function Oh(e,t){function n(){let t=!1,n=new ks,r=null,i=new ks(0,0,0,0);return{setMask:function(n){r!==n&&!t&&(e.colorMask(n,n,n,n),r=n)},setLocked:function(e){t=e},setClear:function(t,r,a,o,s){s===!0&&(t*=o,r*=o,a*=o),n.set(t,r,a,o),i.equals(n)===!1&&(e.clearColor(t,r,a,o),i.copy(n))},reset:function(){t=!1,r=null,i.set(-1,0,0,0)}}}function r(){let n=!1,r=!1,i=null,a=null,o=null;return{setReversed:function(e){if(r!==e){let n=t.get(`EXT_clip_control`);e?n.clipControlEXT(n.LOWER_LEFT_EXT,n.ZERO_TO_ONE_EXT):n.clipControlEXT(n.LOWER_LEFT_EXT,n.NEGATIVE_ONE_TO_ONE_EXT),r=e;let i=o;o=null,this.setClear(i)}},getReversed:function(){return r},setTest:function(t){t?oe(e.DEPTH_TEST):se(e.DEPTH_TEST)},setMask:function(t){i!==t&&!n&&(e.depthMask(t),i=t)},setFunc:function(t){if(r&&(t=Lo[t]),a!==t){switch(t){case 0:e.depthFunc(e.NEVER);break;case 1:e.depthFunc(e.ALWAYS);break;case 2:e.depthFunc(e.LESS);break;case 3:e.depthFunc(e.LEQUAL);break;case 4:e.depthFunc(e.EQUAL);break;case 5:e.depthFunc(e.GEQUAL);break;case 6:e.depthFunc(e.GREATER);break;case 7:e.depthFunc(e.NOTEQUAL);break;default:e.depthFunc(e.LEQUAL)}a=t}},setLocked:function(e){n=e},setClear:function(t){o!==t&&(o=t,r&&(t=1-t),e.clearDepth(t))},reset:function(){n=!1,i=null,a=null,o=null,r=!1}}}function i(){let t=!1,n=null,r=null,i=null,a=null,o=null,s=null,c=null,l=null;return{setTest:function(n){t||(n?oe(e.STENCIL_TEST):se(e.STENCIL_TEST))},setMask:function(r){n!==r&&!t&&(e.stencilMask(r),n=r)},setFunc:function(t,n,o){(r!==t||i!==n||a!==o)&&(e.stencilFunc(t,n,o),r=t,i=n,a=o)},setOp:function(t,n,r){(o!==t||s!==n||c!==r)&&(e.stencilOp(t,n,r),o=t,s=n,c=r)},setLocked:function(e){t=e},setClear:function(t){l!==t&&(e.clearStencil(t),l=t)},reset:function(){t=!1,n=null,r=null,i=null,a=null,o=null,s=null,c=null,l=null}}}let a=new n,o=new r,s=new i,c=new WeakMap,l=new WeakMap,u={},d={},f={},p=new WeakMap,m=[],h=null,g=!1,_=null,v=null,y=null,b=null,x=null,S=null,C=null,w=new mc(0,0,0),T=0,E=!1,D=null,O=null,k=null,A=null,j=null,M=e.getParameter(e.MAX_COMBINED_TEXTURE_IMAGE_UNITS),N=!1,P=0,F=e.getParameter(e.VERSION);F.indexOf(`WebGL`)===-1?F.indexOf(`OpenGL ES`)!==-1&&(P=parseFloat(/^OpenGL ES (\d)/.exec(F)[1]),N=P>=2):(P=parseFloat(/^WebGL (\d)/.exec(F)[1]),N=P>=1);let ee=null,te={},I=e.getParameter(e.SCISSOR_BOX),L=e.getParameter(e.VIEWPORT),ne=new ks().fromArray(I),re=new ks().fromArray(L);function ie(t,n,r,i){let a=new Uint8Array(4),o=e.createTexture();e.bindTexture(t,o),e.texParameteri(t,e.TEXTURE_MIN_FILTER,e.NEAREST),e.texParameteri(t,e.TEXTURE_MAG_FILTER,e.NEAREST);for(let o=0;o<r;o++)t===e.TEXTURE_3D||t===e.TEXTURE_2D_ARRAY?e.texImage3D(n,0,e.RGBA,1,1,i,0,e.RGBA,e.UNSIGNED_BYTE,a):e.texImage2D(n+o,0,e.RGBA,1,1,0,e.RGBA,e.UNSIGNED_BYTE,a);return o}let ae={};ae[e.TEXTURE_2D]=ie(e.TEXTURE_2D,e.TEXTURE_2D,1),ae[e.TEXTURE_CUBE_MAP]=ie(e.TEXTURE_CUBE_MAP,e.TEXTURE_CUBE_MAP_POSITIVE_X,6),ae[e.TEXTURE_2D_ARRAY]=ie(e.TEXTURE_2D_ARRAY,e.TEXTURE_2D_ARRAY,1,1),ae[e.TEXTURE_3D]=ie(e.TEXTURE_3D,e.TEXTURE_3D,1,1),a.setClear(0,0,0,1),o.setClear(1),s.setClear(0),oe(e.DEPTH_TEST),o.setFunc(3),he(!1),ge(1),oe(e.CULL_FACE),pe(0);function oe(t){u[t]!==!0&&(e.enable(t),u[t]=!0)}function se(t){u[t]!==!1&&(e.disable(t),u[t]=!1)}function ce(t,n){return f[t]!==n&&(e.bindFramebuffer(t,n),f[t]=n,t===e.DRAW_FRAMEBUFFER&&(f[e.FRAMEBUFFER]=n),t===e.FRAMEBUFFER&&(f[e.DRAW_FRAMEBUFFER]=n),!0)}function le(t,n){let r=m,i=!1;if(t){r=p.get(n),r===void 0&&(r=[],p.set(n,r));let a=t.textures;if(r.length!==a.length||r[0]!==e.COLOR_ATTACHMENT0){for(let t=0,n=a.length;t<n;t++)r[t]=e.COLOR_ATTACHMENT0+t;r.length=a.length,i=!0}}else r[0]!==e.BACK&&(r[0]=e.BACK,i=!0);i&&e.drawBuffers(r)}function ue(t){return h!==t&&(e.useProgram(t),h=t,!0)}let de={100:e.FUNC_ADD,101:e.FUNC_SUBTRACT,102:e.FUNC_REVERSE_SUBTRACT};de[103]=e.MIN,de[104]=e.MAX;let fe={200:e.ZERO,201:e.ONE,202:e.SRC_COLOR,204:e.SRC_ALPHA,210:e.SRC_ALPHA_SATURATE,208:e.DST_COLOR,206:e.DST_ALPHA,203:e.ONE_MINUS_SRC_COLOR,205:e.ONE_MINUS_SRC_ALPHA,209:e.ONE_MINUS_DST_COLOR,207:e.ONE_MINUS_DST_ALPHA,211:e.CONSTANT_COLOR,212:e.ONE_MINUS_CONSTANT_COLOR,213:e.CONSTANT_ALPHA,214:e.ONE_MINUS_CONSTANT_ALPHA};function pe(t,n,r,i,a,o,s,c,l,u){if(t===0){g===!0&&(se(e.BLEND),g=!1);return}if(g===!1&&(oe(e.BLEND),g=!0),t!==5){if(t!==_||u!==E){if((v!==100||x!==100)&&(e.blendEquation(e.FUNC_ADD),v=100,x=100),u)switch(t){case 1:e.blendFuncSeparate(e.ONE,e.ONE_MINUS_SRC_ALPHA,e.ONE,e.ONE_MINUS_SRC_ALPHA);break;case 2:e.blendFunc(e.ONE,e.ONE);break;case 3:e.blendFuncSeparate(e.ZERO,e.ONE_MINUS_SRC_COLOR,e.ZERO,e.ONE);break;case 4:e.blendFuncSeparate(e.DST_COLOR,e.ONE_MINUS_SRC_ALPHA,e.ZERO,e.ONE);break;default:q(`WebGLState: Invalid blending: `,t)}else switch(t){case 1:e.blendFuncSeparate(e.SRC_ALPHA,e.ONE_MINUS_SRC_ALPHA,e.ONE,e.ONE_MINUS_SRC_ALPHA);break;case 2:e.blendFuncSeparate(e.SRC_ALPHA,e.ONE,e.ONE,e.ONE);break;case 3:q(`WebGLState: SubtractiveBlending requires material.premultipliedAlpha = true`);break;case 4:q(`WebGLState: MultiplyBlending requires material.premultipliedAlpha = true`);break;default:q(`WebGLState: Invalid blending: `,t)}y=null,b=null,S=null,C=null,w.set(0,0,0),T=0,_=t,E=u}return}a||=n,o||=r,s||=i,(n!==v||a!==x)&&(e.blendEquationSeparate(de[n],de[a]),v=n,x=a),(r!==y||i!==b||o!==S||s!==C)&&(e.blendFuncSeparate(fe[r],fe[i],fe[o],fe[s]),y=r,b=i,S=o,C=s),(c.equals(w)===!1||l!==T)&&(e.blendColor(c.r,c.g,c.b,l),w.copy(c),T=l),_=t,E=!1}function me(t,n){t.side===2?se(e.CULL_FACE):oe(e.CULL_FACE);let r=t.side===1;n&&(r=!r),he(r),t.blending===1&&t.transparent===!1?pe(0):pe(t.blending,t.blendEquation,t.blendSrc,t.blendDst,t.blendEquationAlpha,t.blendSrcAlpha,t.blendDstAlpha,t.blendColor,t.blendAlpha,t.premultipliedAlpha),o.setFunc(t.depthFunc),o.setTest(t.depthTest),o.setMask(t.depthWrite),a.setMask(t.colorWrite);let i=t.stencilWrite;s.setTest(i),i&&(s.setMask(t.stencilWriteMask),s.setFunc(t.stencilFunc,t.stencilRef,t.stencilFuncMask),s.setOp(t.stencilFail,t.stencilZFail,t.stencilZPass)),ve(t.polygonOffset,t.polygonOffsetFactor,t.polygonOffsetUnits),t.alphaToCoverage===!0?oe(e.SAMPLE_ALPHA_TO_COVERAGE):se(e.SAMPLE_ALPHA_TO_COVERAGE)}function he(t){D!==t&&(t?e.frontFace(e.CW):e.frontFace(e.CCW),D=t)}function ge(t){t===0?se(e.CULL_FACE):(oe(e.CULL_FACE),t!==O&&(t===1?e.cullFace(e.BACK):t===2?e.cullFace(e.FRONT):e.cullFace(e.FRONT_AND_BACK))),O=t}function _e(t){t!==k&&(N&&e.lineWidth(t),k=t)}function ve(t,n,r){t?(oe(e.POLYGON_OFFSET_FILL),(A!==n||j!==r)&&(A=n,j=r,o.getReversed()&&(n=-n),e.polygonOffset(n,r))):se(e.POLYGON_OFFSET_FILL)}function ye(t){t?oe(e.SCISSOR_TEST):se(e.SCISSOR_TEST)}function R(t){t===void 0&&(t=e.TEXTURE0+M-1),ee!==t&&(e.activeTexture(t),ee=t)}function be(t,n,r){r===void 0&&(r=ee===null?e.TEXTURE0+M-1:ee);let i=te[r];i===void 0&&(i={type:void 0,texture:void 0},te[r]=i),(i.type!==t||i.texture!==n)&&(ee!==r&&(e.activeTexture(r),ee=r),e.bindTexture(t,n||ae[t]),i.type=t,i.texture=n)}function xe(){let t=te[ee];t!==void 0&&t.type!==void 0&&(e.bindTexture(t.type,null),t.type=void 0,t.texture=void 0)}function Se(){try{e.compressedTexImage2D(...arguments)}catch(e){q(`WebGLState:`,e)}}function z(){try{e.compressedTexImage3D(...arguments)}catch(e){q(`WebGLState:`,e)}}function Ce(){try{e.texSubImage2D(...arguments)}catch(e){q(`WebGLState:`,e)}}function B(){try{e.texSubImage3D(...arguments)}catch(e){q(`WebGLState:`,e)}}function V(){try{e.compressedTexSubImage2D(...arguments)}catch(e){q(`WebGLState:`,e)}}function we(){try{e.compressedTexSubImage3D(...arguments)}catch(e){q(`WebGLState:`,e)}}function Te(){try{e.texStorage2D(...arguments)}catch(e){q(`WebGLState:`,e)}}function Ee(){try{e.texStorage3D(...arguments)}catch(e){q(`WebGLState:`,e)}}function De(){try{e.texImage2D(...arguments)}catch(e){q(`WebGLState:`,e)}}function Oe(){try{e.texImage3D(...arguments)}catch(e){q(`WebGLState:`,e)}}function ke(t){return d[t]===void 0?e.getParameter(t):d[t]}function Ae(t,n){d[t]!==n&&(e.pixelStorei(t,n),d[t]=n)}function je(t){ne.equals(t)===!1&&(e.scissor(t.x,t.y,t.z,t.w),ne.copy(t))}function Me(t){re.equals(t)===!1&&(e.viewport(t.x,t.y,t.z,t.w),re.copy(t))}function Ne(t,n){let r=l.get(n);r===void 0&&(r=new WeakMap,l.set(n,r));let i=r.get(t);i===void 0&&(i=e.getUniformBlockIndex(n,t.name),r.set(t,i))}function Pe(t,n){let r=l.get(n).get(t);c.get(n)!==r&&(e.uniformBlockBinding(n,r,t.__bindingPointIndex),c.set(n,r))}function Fe(){e.disable(e.BLEND),e.disable(e.CULL_FACE),e.disable(e.DEPTH_TEST),e.disable(e.POLYGON_OFFSET_FILL),e.disable(e.SCISSOR_TEST),e.disable(e.STENCIL_TEST),e.disable(e.SAMPLE_ALPHA_TO_COVERAGE),e.blendEquation(e.FUNC_ADD),e.blendFunc(e.ONE,e.ZERO),e.blendFuncSeparate(e.ONE,e.ZERO,e.ONE,e.ZERO),e.blendColor(0,0,0,0),e.colorMask(!0,!0,!0,!0),e.clearColor(0,0,0,0),e.depthMask(!0),e.depthFunc(e.LESS),o.setReversed(!1),e.clearDepth(1),e.stencilMask(4294967295),e.stencilFunc(e.ALWAYS,0,4294967295),e.stencilOp(e.KEEP,e.KEEP,e.KEEP),e.clearStencil(0),e.cullFace(e.BACK),e.frontFace(e.CCW),e.polygonOffset(0,0),e.activeTexture(e.TEXTURE0),e.bindFramebuffer(e.FRAMEBUFFER,null),e.bindFramebuffer(e.DRAW_FRAMEBUFFER,null),e.bindFramebuffer(e.READ_FRAMEBUFFER,null),e.useProgram(null),e.lineWidth(1),e.scissor(0,0,e.canvas.width,e.canvas.height),e.viewport(0,0,e.canvas.width,e.canvas.height),e.pixelStorei(e.PACK_ALIGNMENT,4),e.pixelStorei(e.UNPACK_ALIGNMENT,4),e.pixelStorei(e.UNPACK_FLIP_Y_WEBGL,!1),e.pixelStorei(e.UNPACK_PREMULTIPLY_ALPHA_WEBGL,!1),e.pixelStorei(e.UNPACK_COLORSPACE_CONVERSION_WEBGL,e.BROWSER_DEFAULT_WEBGL),e.pixelStorei(e.PACK_ROW_LENGTH,0),e.pixelStorei(e.PACK_SKIP_PIXELS,0),e.pixelStorei(e.PACK_SKIP_ROWS,0),e.pixelStorei(e.UNPACK_ROW_LENGTH,0),e.pixelStorei(e.UNPACK_IMAGE_HEIGHT,0),e.pixelStorei(e.UNPACK_SKIP_PIXELS,0),e.pixelStorei(e.UNPACK_SKIP_ROWS,0),e.pixelStorei(e.UNPACK_SKIP_IMAGES,0),u={},d={},ee=null,te={},f={},p=new WeakMap,m=[],h=null,g=!1,_=null,v=null,y=null,b=null,x=null,S=null,C=null,w=new mc(0,0,0),T=0,E=!1,D=null,O=null,k=null,A=null,j=null,ne.set(0,0,e.canvas.width,e.canvas.height),re.set(0,0,e.canvas.width,e.canvas.height),a.reset(),o.reset(),s.reset()}return{buffers:{color:a,depth:o,stencil:s},enable:oe,disable:se,bindFramebuffer:ce,drawBuffers:le,useProgram:ue,setBlending:pe,setMaterial:me,setFlipSided:he,setCullFace:ge,setLineWidth:_e,setPolygonOffset:ve,setScissorTest:ye,activeTexture:R,bindTexture:be,unbindTexture:xe,compressedTexImage2D:Se,compressedTexImage3D:z,texImage2D:De,texImage3D:Oe,pixelStorei:Ae,getParameter:ke,updateUBOMapping:Ne,uniformBlockBinding:Pe,texStorage2D:Te,texStorage3D:Ee,texSubImage2D:Ce,texSubImage3D:B,compressedTexSubImage2D:V,compressedTexSubImage3D:we,scissor:je,viewport:Me,reset:Fe}}function kh(e,t,n,r,i,a,o){let s=t.has(`WEBGL_multisampled_render_to_texture`)?t.get(`WEBGL_multisampled_render_to_texture`):null,c=typeof navigator>`u`?!1:/OculusBrowser/g.test(navigator.userAgent),l=new Y,u=new WeakMap,d=new Set,f,p=new WeakMap,m=!1;try{m=typeof OffscreenCanvas<`u`&&new OffscreenCanvas(1,1).getContext(`2d`)!==null}catch{}function h(e,t){return m?new OffscreenCanvas(e,t):Ao(`canvas`)}function g(e,t,n){let r=1,i=Se(e);if((i.width>n||i.height>n)&&(r=n/Math.max(i.width,i.height)),r<1){if(typeof HTMLImageElement<`u`&&e instanceof HTMLImageElement||typeof HTMLCanvasElement<`u`&&e instanceof HTMLCanvasElement||typeof ImageBitmap<`u`&&e instanceof ImageBitmap||typeof VideoFrame<`u`&&e instanceof VideoFrame){let n=Math.floor(r*i.width),a=Math.floor(r*i.height);f===void 0&&(f=h(n,a));let o=t?h(n,a):f;return o.width=n,o.height=a,o.getContext(`2d`).drawImage(e,0,0,n,a),K(`WebGLRenderer: Texture has been resized from (`+i.width+`x`+i.height+`) to (`+n+`x`+a+`).`),o}return`data`in e&&K(`WebGLRenderer: Image in DataTexture is too big (`+i.width+`x`+i.height+`).`),e}return e}function _(e){return e.generateMipmaps}function v(t){e.generateMipmap(t)}function y(t){return t.isWebGLCubeRenderTarget?e.TEXTURE_CUBE_MAP:t.isWebGL3DRenderTarget?e.TEXTURE_3D:t.isWebGLArrayRenderTarget||t.isCompressedArrayTexture?e.TEXTURE_2D_ARRAY:e.TEXTURE_2D}function b(n,r,i,a,o,s=!1){if(n!==null){if(e[n]!==void 0)return e[n];K(`WebGLRenderer: Attempt to use non-existing WebGL internal format '`+n+`'`)}let c;a&&(c=t.get(`EXT_texture_norm16`),c||K(`WebGLRenderer: Unable to use normalized textures without EXT_texture_norm16 extension`));let l=r;if(r===e.RED&&(i===e.FLOAT&&(l=e.R32F),i===e.HALF_FLOAT&&(l=e.R16F),i===e.UNSIGNED_BYTE&&(l=e.R8),i===e.UNSIGNED_SHORT&&c&&(l=c.R16_EXT),i===e.SHORT&&c&&(l=c.R16_SNORM_EXT)),r===e.RED_INTEGER&&(i===e.UNSIGNED_BYTE&&(l=e.R8UI),i===e.UNSIGNED_SHORT&&(l=e.R16UI),i===e.UNSIGNED_INT&&(l=e.R32UI),i===e.BYTE&&(l=e.R8I),i===e.SHORT&&(l=e.R16I),i===e.INT&&(l=e.R32I)),r===e.RG&&(i===e.FLOAT&&(l=e.RG32F),i===e.HALF_FLOAT&&(l=e.RG16F),i===e.UNSIGNED_BYTE&&(l=e.RG8),i===e.UNSIGNED_SHORT&&c&&(l=c.RG16_EXT),i===e.SHORT&&c&&(l=c.RG16_SNORM_EXT)),r===e.RG_INTEGER&&(i===e.UNSIGNED_BYTE&&(l=e.RG8UI),i===e.UNSIGNED_SHORT&&(l=e.RG16UI),i===e.UNSIGNED_INT&&(l=e.RG32UI),i===e.BYTE&&(l=e.RG8I),i===e.SHORT&&(l=e.RG16I),i===e.INT&&(l=e.RG32I)),r===e.RGB_INTEGER&&(i===e.UNSIGNED_BYTE&&(l=e.RGB8UI),i===e.UNSIGNED_SHORT&&(l=e.RGB16UI),i===e.UNSIGNED_INT&&(l=e.RGB32UI),i===e.BYTE&&(l=e.RGB8I),i===e.SHORT&&(l=e.RGB16I),i===e.INT&&(l=e.RGB32I)),r===e.RGBA_INTEGER&&(i===e.UNSIGNED_BYTE&&(l=e.RGBA8UI),i===e.UNSIGNED_SHORT&&(l=e.RGBA16UI),i===e.UNSIGNED_INT&&(l=e.RGBA32UI),i===e.BYTE&&(l=e.RGBA8I),i===e.SHORT&&(l=e.RGBA16I),i===e.INT&&(l=e.RGBA32I)),r===e.RGB&&(i===e.UNSIGNED_SHORT&&c&&(l=c.RGB16_EXT),i===e.SHORT&&c&&(l=c.RGB16_SNORM_EXT),i===e.UNSIGNED_INT_5_9_9_9_REV&&(l=e.RGB9_E5),i===e.UNSIGNED_INT_10F_11F_11F_REV&&(l=e.R11F_G11F_B10F)),r===e.RGBA){let t=s?Co:vs.getTransfer(o);i===e.FLOAT&&(l=e.RGBA32F),i===e.HALF_FLOAT&&(l=e.RGBA16F),i===e.UNSIGNED_BYTE&&(l=t===`srgb`?e.SRGB8_ALPHA8:e.RGBA8),i===e.UNSIGNED_SHORT&&c&&(l=c.RGBA16_EXT),i===e.SHORT&&c&&(l=c.RGBA16_SNORM_EXT),i===e.UNSIGNED_SHORT_4_4_4_4&&(l=e.RGBA4),i===e.UNSIGNED_SHORT_5_5_5_1&&(l=e.RGB5_A1)}return(l===e.R16F||l===e.R32F||l===e.RG16F||l===e.RG32F||l===e.RGBA16F||l===e.RGBA32F)&&t.get(`EXT_color_buffer_float`),l}function x(t,n){let r;return t?n===null||n===1014||n===1020?r=e.DEPTH24_STENCIL8:n===1015?r=e.DEPTH32F_STENCIL8:n===1012&&(r=e.DEPTH24_STENCIL8,K(`DepthTexture: 16 bit depth attachment is not supported with stencil. Using 24-bit attachment.`)):n===null||n===1014||n===1020?r=e.DEPTH_COMPONENT24:n===1015?r=e.DEPTH_COMPONENT32F:n===1012&&(r=e.DEPTH_COMPONENT16),r}function S(e,t){return _(e)===!0||e.isFramebufferTexture&&e.minFilter!==1003&&e.minFilter!==1006?Math.log2(Math.max(t.width,t.height))+1:e.mipmaps!==void 0&&e.mipmaps.length>0?e.mipmaps.length:e.isCompressedTexture&&Array.isArray(e.image)?t.mipmaps.length:1}function C(e){let t=e.target;t.removeEventListener(`dispose`,C),T(t),t.isVideoTexture&&u.delete(t),t.isHTMLTexture&&d.delete(t)}function w(e){let t=e.target;t.removeEventListener(`dispose`,w),D(t)}function T(e){let t=r.get(e);if(t.__webglInit===void 0)return;let n=e.source,i=p.get(n);if(i){let r=i[t.__cacheKey];r.usedTimes--,r.usedTimes===0&&E(e),Object.keys(i).length===0&&p.delete(n)}r.remove(e)}function E(t){let n=r.get(t);e.deleteTexture(n.__webglTexture);let i=t.source,a=p.get(i);delete a[n.__cacheKey],o.memory.textures--}function D(t){let n=r.get(t);if(t.depthTexture&&(t.depthTexture.dispose(),r.remove(t.depthTexture)),t.isWebGLCubeRenderTarget)for(let t=0;t<6;t++){if(Array.isArray(n.__webglFramebuffer[t]))for(let r=0;r<n.__webglFramebuffer[t].length;r++)e.deleteFramebuffer(n.__webglFramebuffer[t][r]);else e.deleteFramebuffer(n.__webglFramebuffer[t]);n.__webglDepthbuffer&&e.deleteRenderbuffer(n.__webglDepthbuffer[t])}else{if(Array.isArray(n.__webglFramebuffer))for(let t=0;t<n.__webglFramebuffer.length;t++)e.deleteFramebuffer(n.__webglFramebuffer[t]);else e.deleteFramebuffer(n.__webglFramebuffer);if(n.__webglDepthbuffer&&e.deleteRenderbuffer(n.__webglDepthbuffer),n.__webglMultisampledFramebuffer&&e.deleteFramebuffer(n.__webglMultisampledFramebuffer),n.__webglColorRenderbuffer)for(let t=0;t<n.__webglColorRenderbuffer.length;t++)n.__webglColorRenderbuffer[t]&&e.deleteRenderbuffer(n.__webglColorRenderbuffer[t]);n.__webglDepthRenderbuffer&&e.deleteRenderbuffer(n.__webglDepthRenderbuffer)}let i=t.textures;for(let t=0,n=i.length;t<n;t++){let n=r.get(i[t]);n.__webglTexture&&(e.deleteTexture(n.__webglTexture),o.memory.textures--),r.remove(i[t])}r.remove(t)}let O=0;function k(){O=0}function A(){return O}function j(e){O=e}function M(){let e=O;return e>=i.maxTextures&&K(`WebGLTextures: Trying to use `+(e+1)+` texture units while this GPU supports only `+i.maxTextures),O+=1,e}function N(e){let t=[];return t.push(e.wrapS),t.push(e.wrapT),t.push(e.wrapR||0),t.push(e.magFilter),t.push(e.minFilter),t.push(e.anisotropy),t.push(e.internalFormat),t.push(e.format),t.push(e.type),t.push(e.generateMipmaps),t.push(e.premultiplyAlpha),t.push(e.flipY),t.push(e.unpackAlignment),t.push(e.colorSpace),t.join()}function P(t,i){let a=r.get(t);if(t.isVideoTexture&&be(t),t.isRenderTargetTexture===!1&&t.isExternalTexture!==!0&&t.version>0&&a.__version!==t.version){let e=t.image;if(e===null)K(`WebGLRenderer: Texture marked for update but no image data found.`);else if(e.complete===!1)K(`WebGLRenderer: Texture marked for update but image is incomplete`);else{se(a,t,i);return}}else t.isExternalTexture&&(a.__webglTexture=t.sourceTexture?t.sourceTexture:null);n.bindTexture(e.TEXTURE_2D,a.__webglTexture,e.TEXTURE0+i)}function F(t,i){let a=r.get(t);if(t.isRenderTargetTexture===!1&&t.version>0&&a.__version!==t.version){se(a,t,i);return}t.isExternalTexture&&(a.__webglTexture=t.sourceTexture?t.sourceTexture:null),n.bindTexture(e.TEXTURE_2D_ARRAY,a.__webglTexture,e.TEXTURE0+i)}function ee(t,i){let a=r.get(t);if(t.isRenderTargetTexture===!1&&t.version>0&&a.__version!==t.version){se(a,t,i);return}n.bindTexture(e.TEXTURE_3D,a.__webglTexture,e.TEXTURE0+i)}function te(t,i){let a=r.get(t);if(t.isCubeDepthTexture!==!0&&t.version>0&&a.__version!==t.version){ce(a,t,i);return}n.bindTexture(e.TEXTURE_CUBE_MAP,a.__webglTexture,e.TEXTURE0+i)}let I={[Qi]:e.REPEAT,[$i]:e.CLAMP_TO_EDGE,[ea]:e.MIRRORED_REPEAT},L={[ta]:e.NEAREST,[na]:e.NEAREST_MIPMAP_NEAREST,[ra]:e.NEAREST_MIPMAP_LINEAR,[ia]:e.LINEAR,[aa]:e.LINEAR_MIPMAP_NEAREST,[oa]:e.LINEAR_MIPMAP_LINEAR},ne={512:e.NEVER,519:e.ALWAYS,513:e.LESS,515:e.LEQUAL,514:e.EQUAL,518:e.GEQUAL,516:e.GREATER,517:e.NOTEQUAL};function re(n,a){if(a.type===1015&&t.has(`OES_texture_float_linear`)===!1&&(a.magFilter===1006||a.magFilter===1007||a.magFilter===1005||a.magFilter===1008||a.minFilter===1006||a.minFilter===1007||a.minFilter===1005||a.minFilter===1008)&&K(`WebGLRenderer: Unable to use linear filtering with floating point textures. OES_texture_float_linear not supported on this device.`),e.texParameteri(n,e.TEXTURE_WRAP_S,I[a.wrapS]),e.texParameteri(n,e.TEXTURE_WRAP_T,I[a.wrapT]),(n===e.TEXTURE_3D||n===e.TEXTURE_2D_ARRAY)&&e.texParameteri(n,e.TEXTURE_WRAP_R,I[a.wrapR]),e.texParameteri(n,e.TEXTURE_MAG_FILTER,L[a.magFilter]),e.texParameteri(n,e.TEXTURE_MIN_FILTER,L[a.minFilter]),a.compareFunction&&(e.texParameteri(n,e.TEXTURE_COMPARE_MODE,e.COMPARE_REF_TO_TEXTURE),e.texParameteri(n,e.TEXTURE_COMPARE_FUNC,ne[a.compareFunction])),t.has(`EXT_texture_filter_anisotropic`)===!0){if(a.magFilter===1003||a.minFilter!==1005&&a.minFilter!==1008||a.type===1015&&t.has(`OES_texture_float_linear`)===!1)return;if(a.anisotropy>1||r.get(a).__currentAnisotropy){let o=t.get(`EXT_texture_filter_anisotropic`);e.texParameterf(n,o.TEXTURE_MAX_ANISOTROPY_EXT,Math.min(a.anisotropy,i.getMaxAnisotropy())),r.get(a).__currentAnisotropy=a.anisotropy}}}function ie(t,n){let r=!1;t.__webglInit===void 0&&(t.__webglInit=!0,n.addEventListener(`dispose`,C));let i=n.source,a=p.get(i);a===void 0&&(a={},p.set(i,a));let s=N(n);if(s!==t.__cacheKey){a[s]===void 0&&(a[s]={texture:e.createTexture(),usedTimes:0},o.memory.textures++,r=!0),a[s].usedTimes++;let i=a[t.__cacheKey];i!==void 0&&(a[t.__cacheKey].usedTimes--,i.usedTimes===0&&E(n)),t.__cacheKey=s,t.__webglTexture=a[s].texture}return r}function ae(e,t,n){return Math.floor(Math.floor(e/n)/t)}function oe(t,r,i,a){let o=t.updateRanges;if(o.length===0)n.texSubImage2D(e.TEXTURE_2D,0,0,0,r.width,r.height,i,a,r.data);else{o.sort((e,t)=>e.start-t.start);let s=0;for(let e=1;e<o.length;e++){let t=o[s],n=o[e],i=t.start+t.count,a=ae(n.start,r.width,4),c=ae(t.start,r.width,4);n.start<=i+1&&a===c&&ae(n.start+n.count-1,r.width,4)===a?t.count=Math.max(t.count,n.start+n.count-t.start):(++s,o[s]=n)}o.length=s+1;let c=n.getParameter(e.UNPACK_ROW_LENGTH),l=n.getParameter(e.UNPACK_SKIP_PIXELS),u=n.getParameter(e.UNPACK_SKIP_ROWS);n.pixelStorei(e.UNPACK_ROW_LENGTH,r.width);for(let t=0,s=o.length;t<s;t++){let s=o[t],c=Math.floor(s.start/4),l=Math.ceil(s.count/4),u=c%r.width,d=Math.floor(c/r.width),f=l;n.pixelStorei(e.UNPACK_SKIP_PIXELS,u),n.pixelStorei(e.UNPACK_SKIP_ROWS,d),n.texSubImage2D(e.TEXTURE_2D,0,u,d,f,1,i,a,r.data)}t.clearUpdateRanges(),n.pixelStorei(e.UNPACK_ROW_LENGTH,c),n.pixelStorei(e.UNPACK_SKIP_PIXELS,l),n.pixelStorei(e.UNPACK_SKIP_ROWS,u)}}function se(t,o,s){let c=e.TEXTURE_2D;(o.isDataArrayTexture||o.isCompressedArrayTexture)&&(c=e.TEXTURE_2D_ARRAY),o.isData3DTexture&&(c=e.TEXTURE_3D);let l=ie(t,o),u=o.source;n.bindTexture(c,t.__webglTexture,e.TEXTURE0+s);let f=r.get(u);if(u.version!==f.__version||l===!0){if(n.activeTexture(e.TEXTURE0+s),!(typeof ImageBitmap<`u`&&o.image instanceof ImageBitmap)){let t=vs.getPrimaries(vs.workingColorSpace),r=o.colorSpace===``?null:vs.getPrimaries(o.colorSpace),i=o.colorSpace===``||t===r?e.NONE:e.BROWSER_DEFAULT_WEBGL;n.pixelStorei(e.UNPACK_FLIP_Y_WEBGL,o.flipY),n.pixelStorei(e.UNPACK_PREMULTIPLY_ALPHA_WEBGL,o.premultiplyAlpha),n.pixelStorei(e.UNPACK_COLORSPACE_CONVERSION_WEBGL,i)}n.pixelStorei(e.UNPACK_ALIGNMENT,o.unpackAlignment);let t=g(o.image,!1,i.maxTextureSize);t=xe(o,t);let r=a.convert(o.format,o.colorSpace),p=a.convert(o.type),m=b(o.internalFormat,r,p,o.normalized,o.colorSpace,o.isVideoTexture);re(c,o);let h,y=o.mipmaps,C=o.isVideoTexture!==!0,w=f.__version===void 0||l===!0,T=u.dataReady,E=S(o,t);if(o.isDepthTexture)m=x(o.format===wa,o.type),w&&(C?n.texStorage2D(e.TEXTURE_2D,1,m,t.width,t.height):n.texImage2D(e.TEXTURE_2D,0,m,t.width,t.height,0,r,p,null));else if(o.isDataTexture){if(y.length>0){C&&w&&n.texStorage2D(e.TEXTURE_2D,E,m,y[0].width,y[0].height);for(let t=0,i=y.length;t<i;t++)h=y[t],C?T&&n.texSubImage2D(e.TEXTURE_2D,t,0,0,h.width,h.height,r,p,h.data):n.texImage2D(e.TEXTURE_2D,t,m,h.width,h.height,0,r,p,h.data);o.generateMipmaps=!1}else C?(w&&n.texStorage2D(e.TEXTURE_2D,E,m,t.width,t.height),T&&oe(o,t,r,p)):n.texImage2D(e.TEXTURE_2D,0,m,t.width,t.height,0,r,p,t.data)}else if(o.isCompressedTexture){if(o.isCompressedArrayTexture){C&&w&&n.texStorage3D(e.TEXTURE_2D_ARRAY,E,m,y[0].width,y[0].height,t.depth);for(let i=0,a=y.length;i<a;i++)if(h=y[i],o.format!==1023){if(r!==null){if(C){if(T){if(o.layerUpdates.size>0){let t=Cf(h.width,h.height,o.format,o.type);for(let a of o.layerUpdates){let o=h.data.subarray(a*t/h.data.BYTES_PER_ELEMENT,(a+1)*t/h.data.BYTES_PER_ELEMENT);n.compressedTexSubImage3D(e.TEXTURE_2D_ARRAY,i,0,0,a,h.width,h.height,1,r,o)}}else n.compressedTexSubImage3D(e.TEXTURE_2D_ARRAY,i,0,0,0,h.width,h.height,t.depth,r,h.data)}}else n.compressedTexImage3D(e.TEXTURE_2D_ARRAY,i,m,h.width,h.height,t.depth,0,h.data,0,0)}else K(`WebGLRenderer: Attempt to load unsupported compressed texture format in .uploadTexture()`)}else C?T&&n.texSubImage3D(e.TEXTURE_2D_ARRAY,i,0,0,0,h.width,h.height,t.depth,r,p,h.data):n.texImage3D(e.TEXTURE_2D_ARRAY,i,m,h.width,h.height,t.depth,0,r,p,h.data);o.layerUpdates.size>0&&o.clearLayerUpdates()}else{C&&w&&n.texStorage2D(e.TEXTURE_2D,E,m,y[0].width,y[0].height);for(let t=0,i=y.length;t<i;t++)h=y[t],o.format===1023?C?T&&n.texSubImage2D(e.TEXTURE_2D,t,0,0,h.width,h.height,r,p,h.data):n.texImage2D(e.TEXTURE_2D,t,m,h.width,h.height,0,r,p,h.data):r===null?K(`WebGLRenderer: Attempt to load unsupported compressed texture format in .uploadTexture()`):C?T&&n.compressedTexSubImage2D(e.TEXTURE_2D,t,0,0,h.width,h.height,r,h.data):n.compressedTexImage2D(e.TEXTURE_2D,t,m,h.width,h.height,0,h.data)}}else if(o.isDataArrayTexture){if(C){if(w&&n.texStorage3D(e.TEXTURE_2D_ARRAY,E,m,t.width,t.height,t.depth),T){if(o.layerUpdates.size>0){let i=Cf(t.width,t.height,o.format,o.type);for(let a of o.layerUpdates){let o=t.data.subarray(a*i/t.data.BYTES_PER_ELEMENT,(a+1)*i/t.data.BYTES_PER_ELEMENT);n.texSubImage3D(e.TEXTURE_2D_ARRAY,0,0,0,a,t.width,t.height,1,r,p,o)}o.clearLayerUpdates()}else n.texSubImage3D(e.TEXTURE_2D_ARRAY,0,0,0,0,t.width,t.height,t.depth,r,p,t.data)}}else n.texImage3D(e.TEXTURE_2D_ARRAY,0,m,t.width,t.height,t.depth,0,r,p,t.data)}else if(o.isData3DTexture)C?(w&&n.texStorage3D(e.TEXTURE_3D,E,m,t.width,t.height,t.depth),T&&n.texSubImage3D(e.TEXTURE_3D,0,0,0,0,t.width,t.height,t.depth,r,p,t.data)):n.texImage3D(e.TEXTURE_3D,0,m,t.width,t.height,t.depth,0,r,p,t.data);else if(o.isFramebufferTexture){if(w){if(C)n.texStorage2D(e.TEXTURE_2D,E,m,t.width,t.height);else{let i=t.width,a=t.height;for(let t=0;t<E;t++)n.texImage2D(e.TEXTURE_2D,t,m,i,a,0,r,p,null),i>>=1,a>>=1}}}else if(o.isHTMLTexture){if(`texElementImage2D`in e){let n=e.canvas;if(n.hasAttribute(`layoutsubtree`)||n.setAttribute(`layoutsubtree`,`true`),t.parentNode!==n){n.appendChild(t),d.add(o),n.onpaint=e=>{let t=e.changedElements;for(let e of d)t.includes(e.image)&&(e.needsUpdate=!0)},n.requestPaint();return}if(e.texElementImage2D.length===3)e.texElementImage2D(e.TEXTURE_2D,e.RGBA8,t);else{let n=e.RGBA,r=e.RGBA,i=e.UNSIGNED_BYTE;e.texElementImage2D(e.TEXTURE_2D,0,n,r,i,t)}e.texParameteri(e.TEXTURE_2D,e.TEXTURE_MIN_FILTER,e.LINEAR),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_WRAP_S,e.CLAMP_TO_EDGE),e.texParameteri(e.TEXTURE_2D,e.TEXTURE_WRAP_T,e.CLAMP_TO_EDGE)}}else if(y.length>0){if(C&&w){let t=Se(y[0]);n.texStorage2D(e.TEXTURE_2D,E,m,t.width,t.height)}for(let t=0,i=y.length;t<i;t++)h=y[t],C?T&&n.texSubImage2D(e.TEXTURE_2D,t,0,0,r,p,h):n.texImage2D(e.TEXTURE_2D,t,m,r,p,h);o.generateMipmaps=!1}else if(C){if(w){let r=Se(t);n.texStorage2D(e.TEXTURE_2D,E,m,r.width,r.height)}T&&n.texSubImage2D(e.TEXTURE_2D,0,0,0,r,p,t)}else n.texImage2D(e.TEXTURE_2D,0,m,r,p,t);_(o)&&v(c),f.__version=u.version,o.onUpdate&&o.onUpdate(o)}t.__version=o.version}function ce(t,o,s){if(o.image.length!==6)return;let c=ie(t,o),l=o.source;n.bindTexture(e.TEXTURE_CUBE_MAP,t.__webglTexture,e.TEXTURE0+s);let u=r.get(l);if(l.version!==u.__version||c===!0){n.activeTexture(e.TEXTURE0+s);let t=vs.getPrimaries(vs.workingColorSpace),r=o.colorSpace===``?null:vs.getPrimaries(o.colorSpace),d=o.colorSpace===``||t===r?e.NONE:e.BROWSER_DEFAULT_WEBGL;n.pixelStorei(e.UNPACK_FLIP_Y_WEBGL,o.flipY),n.pixelStorei(e.UNPACK_PREMULTIPLY_ALPHA_WEBGL,o.premultiplyAlpha),n.pixelStorei(e.UNPACK_ALIGNMENT,o.unpackAlignment),n.pixelStorei(e.UNPACK_COLORSPACE_CONVERSION_WEBGL,d);let f=o.isCompressedTexture||o.image[0].isCompressedTexture,p=o.image[0]&&o.image[0].isDataTexture,m=[];for(let e=0;e<6;e++)!f&&!p?m[e]=g(o.image[e],!0,i.maxCubemapSize):m[e]=p?o.image[e].image:o.image[e],m[e]=xe(o,m[e]);let h=m[0],y=a.convert(o.format,o.colorSpace),x=a.convert(o.type),C=b(o.internalFormat,y,x,o.normalized,o.colorSpace),w=o.isVideoTexture!==!0,T=u.__version===void 0||c===!0,E=l.dataReady,D=S(o,h);re(e.TEXTURE_CUBE_MAP,o);let O;if(f){w&&T&&n.texStorage2D(e.TEXTURE_CUBE_MAP,D,C,h.width,h.height);for(let t=0;t<6;t++){O=m[t].mipmaps;for(let r=0;r<O.length;r++){let i=O[r];o.format===1023?w?E&&n.texSubImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,r,0,0,i.width,i.height,y,x,i.data):n.texImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,r,C,i.width,i.height,0,y,x,i.data):y===null?K(`WebGLRenderer: Attempt to load unsupported compressed texture format in .setTextureCube()`):w?E&&n.compressedTexSubImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,r,0,0,i.width,i.height,y,i.data):n.compressedTexImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,r,C,i.width,i.height,0,i.data)}}}else{if(O=o.mipmaps,w&&T){O.length>0&&D++;let t=Se(m[0]);n.texStorage2D(e.TEXTURE_CUBE_MAP,D,C,t.width,t.height)}for(let t=0;t<6;t++)if(p){w?E&&n.texSubImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,0,0,0,m[t].width,m[t].height,y,x,m[t].data):n.texImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,0,C,m[t].width,m[t].height,0,y,x,m[t].data);for(let r=0;r<O.length;r++){let i=O[r].image[t].image;w?E&&n.texSubImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,r+1,0,0,i.width,i.height,y,x,i.data):n.texImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,r+1,C,i.width,i.height,0,y,x,i.data)}}else{w?E&&n.texSubImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,0,0,0,y,x,m[t]):n.texImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,0,C,y,x,m[t]);for(let r=0;r<O.length;r++){let i=O[r];w?E&&n.texSubImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,r+1,0,0,y,x,i.image[t]):n.texImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+t,r+1,C,y,x,i.image[t])}}}_(o)&&v(e.TEXTURE_CUBE_MAP),u.__version=l.version,o.onUpdate&&o.onUpdate(o)}t.__version=o.version}function le(t,i,o,c,l,u){let d=a.convert(o.format,o.colorSpace),f=a.convert(o.type),p=b(o.internalFormat,d,f,o.normalized,o.colorSpace),m=r.get(i),h=r.get(o);if(h.__renderTarget=i,!m.__hasExternalTextures){let t=Math.max(1,i.width>>u),r=Math.max(1,i.height>>u);l===e.TEXTURE_3D||l===e.TEXTURE_2D_ARRAY?n.texImage3D(l,u,p,t,r,i.depth,0,d,f,null):n.texImage2D(l,u,p,t,r,0,d,f,null)}n.bindFramebuffer(e.FRAMEBUFFER,t),R(i)?s.framebufferTexture2DMultisampleEXT(e.FRAMEBUFFER,c,l,h.__webglTexture,0,ye(i)):(l===e.TEXTURE_2D||l>=e.TEXTURE_CUBE_MAP_POSITIVE_X&&l<=e.TEXTURE_CUBE_MAP_NEGATIVE_Z)&&e.framebufferTexture2D(e.FRAMEBUFFER,c,l,h.__webglTexture,u),n.bindFramebuffer(e.FRAMEBUFFER,null)}function ue(t,n,r){if(e.bindRenderbuffer(e.RENDERBUFFER,t),n.depthBuffer){let i=n.depthTexture,a=i&&i.isDepthTexture?i.type:null,o=x(n.stencilBuffer,a),c=n.stencilBuffer?e.DEPTH_STENCIL_ATTACHMENT:e.DEPTH_ATTACHMENT;R(n)?s.renderbufferStorageMultisampleEXT(e.RENDERBUFFER,ye(n),o,n.width,n.height):r?e.renderbufferStorageMultisample(e.RENDERBUFFER,ye(n),o,n.width,n.height):e.renderbufferStorage(e.RENDERBUFFER,o,n.width,n.height),e.framebufferRenderbuffer(e.FRAMEBUFFER,c,e.RENDERBUFFER,t)}else{let t=n.textures;for(let i=0;i<t.length;i++){let o=t[i],c=a.convert(o.format,o.colorSpace),l=a.convert(o.type),u=b(o.internalFormat,c,l,o.normalized,o.colorSpace);R(n)?s.renderbufferStorageMultisampleEXT(e.RENDERBUFFER,ye(n),u,n.width,n.height):r?e.renderbufferStorageMultisample(e.RENDERBUFFER,ye(n),u,n.width,n.height):e.renderbufferStorage(e.RENDERBUFFER,u,n.width,n.height)}}e.bindRenderbuffer(e.RENDERBUFFER,null)}function de(t,i,o){let c=i.isWebGLCubeRenderTarget===!0;if(n.bindFramebuffer(e.FRAMEBUFFER,t),!(i.depthTexture&&i.depthTexture.isDepthTexture))throw Error(`THREE.WebGLTextures: renderTarget.depthTexture must be an instance of THREE.DepthTexture.`);let l=r.get(i.depthTexture);if(l.__renderTarget=i,(!l.__webglTexture||i.depthTexture.image.width!==i.width||i.depthTexture.image.height!==i.height)&&(i.depthTexture.image.width=i.width,i.depthTexture.image.height=i.height,i.depthTexture.needsUpdate=!0),c){if(l.__webglInit===void 0&&(l.__webglInit=!0,i.depthTexture.addEventListener(`dispose`,C)),l.__webglTexture===void 0){l.__webglTexture=e.createTexture(),n.bindTexture(e.TEXTURE_CUBE_MAP,l.__webglTexture),re(e.TEXTURE_CUBE_MAP,i.depthTexture);let t=a.convert(i.depthTexture.format),r=a.convert(i.depthTexture.type),o;i.depthTexture.format===1026?o=e.DEPTH_COMPONENT24:i.depthTexture.format===1027&&(o=e.DEPTH24_STENCIL8);for(let n=0;n<6;n++)e.texImage2D(e.TEXTURE_CUBE_MAP_POSITIVE_X+n,0,o,i.width,i.height,0,t,r,null)}}else P(i.depthTexture,0);let u=l.__webglTexture,d=ye(i),f=c?e.TEXTURE_CUBE_MAP_POSITIVE_X+o:e.TEXTURE_2D,p=i.depthTexture.format===1027?e.DEPTH_STENCIL_ATTACHMENT:e.DEPTH_ATTACHMENT;if(i.depthTexture.format===1026)R(i)?s.framebufferTexture2DMultisampleEXT(e.FRAMEBUFFER,p,f,u,0,d):e.framebufferTexture2D(e.FRAMEBUFFER,p,f,u,0);else if(i.depthTexture.format===1027)R(i)?s.framebufferTexture2DMultisampleEXT(e.FRAMEBUFFER,p,f,u,0,d):e.framebufferTexture2D(e.FRAMEBUFFER,p,f,u,0);else throw Error(`THREE.WebGLTextures: Unknown depthTexture format.`)}function fe(t){let i=r.get(t),a=t.isWebGLCubeRenderTarget===!0;if(i.__boundDepthTexture!==t.depthTexture){let e=t.depthTexture;if(i.__depthDisposeCallback&&i.__depthDisposeCallback(),e){let t=()=>{delete i.__boundDepthTexture,delete i.__depthDisposeCallback,e.removeEventListener(`dispose`,t)};e.addEventListener(`dispose`,t),i.__depthDisposeCallback=t}i.__boundDepthTexture=e}if(t.depthTexture&&!i.__autoAllocateDepthBuffer){if(a)for(let e=0;e<6;e++)de(i.__webglFramebuffer[e],t,e);else{let e=t.texture.mipmaps;e&&e.length>0?de(i.__webglFramebuffer[0],t,0):de(i.__webglFramebuffer,t,0)}}else if(a){i.__webglDepthbuffer=[];for(let r=0;r<6;r++)if(n.bindFramebuffer(e.FRAMEBUFFER,i.__webglFramebuffer[r]),i.__webglDepthbuffer[r]===void 0)i.__webglDepthbuffer[r]=e.createRenderbuffer(),ue(i.__webglDepthbuffer[r],t,!1);else{let n=t.stencilBuffer?e.DEPTH_STENCIL_ATTACHMENT:e.DEPTH_ATTACHMENT,a=i.__webglDepthbuffer[r];e.bindRenderbuffer(e.RENDERBUFFER,a),e.framebufferRenderbuffer(e.FRAMEBUFFER,n,e.RENDERBUFFER,a)}}else{let r=t.texture.mipmaps;if(r&&r.length>0?n.bindFramebuffer(e.FRAMEBUFFER,i.__webglFramebuffer[0]):n.bindFramebuffer(e.FRAMEBUFFER,i.__webglFramebuffer),i.__webglDepthbuffer===void 0)i.__webglDepthbuffer=e.createRenderbuffer(),ue(i.__webglDepthbuffer,t,!1);else{let n=t.stencilBuffer?e.DEPTH_STENCIL_ATTACHMENT:e.DEPTH_ATTACHMENT,r=i.__webglDepthbuffer;e.bindRenderbuffer(e.RENDERBUFFER,r),e.framebufferRenderbuffer(e.FRAMEBUFFER,n,e.RENDERBUFFER,r)}}n.bindFramebuffer(e.FRAMEBUFFER,null)}function pe(t,n,i){let a=r.get(t);n!==void 0&&le(a.__webglFramebuffer,t,t.texture,e.COLOR_ATTACHMENT0,e.TEXTURE_2D,0),i!==void 0&&fe(t)}function me(t){let i=t.texture,s=r.get(t),c=r.get(i);t.addEventListener(`dispose`,w);let l=t.textures,u=t.isWebGLCubeRenderTarget===!0,d=l.length>1;if(d||(c.__webglTexture===void 0&&(c.__webglTexture=e.createTexture()),c.__version=i.version,o.memory.textures++),u){s.__webglFramebuffer=[];for(let t=0;t<6;t++)if(i.mipmaps&&i.mipmaps.length>0){s.__webglFramebuffer[t]=[];for(let n=0;n<i.mipmaps.length;n++)s.__webglFramebuffer[t][n]=e.createFramebuffer()}else s.__webglFramebuffer[t]=e.createFramebuffer()}else{if(i.mipmaps&&i.mipmaps.length>0){s.__webglFramebuffer=[];for(let t=0;t<i.mipmaps.length;t++)s.__webglFramebuffer[t]=e.createFramebuffer()}else s.__webglFramebuffer=e.createFramebuffer();if(d)for(let t=0,n=l.length;t<n;t++){let n=r.get(l[t]);n.__webglTexture===void 0&&(n.__webglTexture=e.createTexture(),o.memory.textures++)}if(t.samples>0&&R(t)===!1){s.__webglMultisampledFramebuffer=e.createFramebuffer(),s.__webglColorRenderbuffer=[],n.bindFramebuffer(e.FRAMEBUFFER,s.__webglMultisampledFramebuffer);for(let n=0;n<l.length;n++){let r=l[n];s.__webglColorRenderbuffer[n]=e.createRenderbuffer(),e.bindRenderbuffer(e.RENDERBUFFER,s.__webglColorRenderbuffer[n]);let i=a.convert(r.format,r.colorSpace),o=a.convert(r.type),c=b(r.internalFormat,i,o,r.normalized,r.colorSpace,t.isXRRenderTarget===!0),u=ye(t);e.renderbufferStorageMultisample(e.RENDERBUFFER,u,c,t.width,t.height),e.framebufferRenderbuffer(e.FRAMEBUFFER,e.COLOR_ATTACHMENT0+n,e.RENDERBUFFER,s.__webglColorRenderbuffer[n])}e.bindRenderbuffer(e.RENDERBUFFER,null),t.depthBuffer&&(s.__webglDepthRenderbuffer=e.createRenderbuffer(),ue(s.__webglDepthRenderbuffer,t,!0)),n.bindFramebuffer(e.FRAMEBUFFER,null)}}if(u){n.bindTexture(e.TEXTURE_CUBE_MAP,c.__webglTexture),re(e.TEXTURE_CUBE_MAP,i);for(let n=0;n<6;n++)if(i.mipmaps&&i.mipmaps.length>0)for(let r=0;r<i.mipmaps.length;r++)le(s.__webglFramebuffer[n][r],t,i,e.COLOR_ATTACHMENT0,e.TEXTURE_CUBE_MAP_POSITIVE_X+n,r);else le(s.__webglFramebuffer[n],t,i,e.COLOR_ATTACHMENT0,e.TEXTURE_CUBE_MAP_POSITIVE_X+n,0);_(i)&&v(e.TEXTURE_CUBE_MAP),n.unbindTexture()}else if(d){for(let i=0,a=l.length;i<a;i++){let a=l[i],o=r.get(a),c=e.TEXTURE_2D;(t.isWebGL3DRenderTarget||t.isWebGLArrayRenderTarget)&&(c=t.isWebGL3DRenderTarget?e.TEXTURE_3D:e.TEXTURE_2D_ARRAY),n.bindTexture(c,o.__webglTexture),re(c,a),le(s.__webglFramebuffer,t,a,e.COLOR_ATTACHMENT0+i,c,0),_(a)&&v(c)}n.unbindTexture()}else{let r=e.TEXTURE_2D;if((t.isWebGL3DRenderTarget||t.isWebGLArrayRenderTarget)&&(r=t.isWebGL3DRenderTarget?e.TEXTURE_3D:e.TEXTURE_2D_ARRAY),n.bindTexture(r,c.__webglTexture),re(r,i),i.mipmaps&&i.mipmaps.length>0)for(let n=0;n<i.mipmaps.length;n++)le(s.__webglFramebuffer[n],t,i,e.COLOR_ATTACHMENT0,r,n);else le(s.__webglFramebuffer,t,i,e.COLOR_ATTACHMENT0,r,0);_(i)&&v(r),n.unbindTexture()}t.depthBuffer&&fe(t)}function he(e){let t=e.textures;for(let i=0,a=t.length;i<a;i++){let a=t[i];if(_(a)){let t=y(e),i=r.get(a).__webglTexture;n.bindTexture(t,i),v(t),n.unbindTexture()}}}let ge=[],_e=[];function ve(t){if(t.samples>0){if(R(t)===!1){let i=t.textures,a=t.width,o=t.height,s=e.COLOR_BUFFER_BIT,l=t.stencilBuffer?e.DEPTH_STENCIL_ATTACHMENT:e.DEPTH_ATTACHMENT,u=r.get(t),d=i.length>1;if(d)for(let t=0;t<i.length;t++)n.bindFramebuffer(e.FRAMEBUFFER,u.__webglMultisampledFramebuffer),e.framebufferRenderbuffer(e.FRAMEBUFFER,e.COLOR_ATTACHMENT0+t,e.RENDERBUFFER,null),n.bindFramebuffer(e.FRAMEBUFFER,u.__webglFramebuffer),e.framebufferTexture2D(e.DRAW_FRAMEBUFFER,e.COLOR_ATTACHMENT0+t,e.TEXTURE_2D,null,0);n.bindFramebuffer(e.READ_FRAMEBUFFER,u.__webglMultisampledFramebuffer);let f=t.texture.mipmaps;f&&f.length>0?n.bindFramebuffer(e.DRAW_FRAMEBUFFER,u.__webglFramebuffer[0]):n.bindFramebuffer(e.DRAW_FRAMEBUFFER,u.__webglFramebuffer);for(let n=0;n<i.length;n++){if(t.resolveDepthBuffer&&(t.depthBuffer&&(s|=e.DEPTH_BUFFER_BIT),t.stencilBuffer&&t.resolveStencilBuffer&&(s|=e.STENCIL_BUFFER_BIT)),d){e.framebufferRenderbuffer(e.READ_FRAMEBUFFER,e.COLOR_ATTACHMENT0,e.RENDERBUFFER,u.__webglColorRenderbuffer[n]);let t=r.get(i[n]).__webglTexture;e.framebufferTexture2D(e.DRAW_FRAMEBUFFER,e.COLOR_ATTACHMENT0,e.TEXTURE_2D,t,0)}e.blitFramebuffer(0,0,a,o,0,0,a,o,s,e.NEAREST),c===!0&&(ge.length=0,_e.length=0,ge.push(e.COLOR_ATTACHMENT0+n),t.depthBuffer&&t.storeMultisampledDepthBuffer===!1&&(ge.push(l),_e.push(l),e.invalidateFramebuffer(e.DRAW_FRAMEBUFFER,_e)),e.invalidateFramebuffer(e.READ_FRAMEBUFFER,ge))}if(n.bindFramebuffer(e.READ_FRAMEBUFFER,null),n.bindFramebuffer(e.DRAW_FRAMEBUFFER,null),d)for(let t=0;t<i.length;t++){n.bindFramebuffer(e.FRAMEBUFFER,u.__webglMultisampledFramebuffer),e.framebufferRenderbuffer(e.FRAMEBUFFER,e.COLOR_ATTACHMENT0+t,e.RENDERBUFFER,u.__webglColorRenderbuffer[t]);let a=r.get(i[t]).__webglTexture;n.bindFramebuffer(e.FRAMEBUFFER,u.__webglFramebuffer),e.framebufferTexture2D(e.DRAW_FRAMEBUFFER,e.COLOR_ATTACHMENT0+t,e.TEXTURE_2D,a,0)}n.bindFramebuffer(e.DRAW_FRAMEBUFFER,u.__webglMultisampledFramebuffer)}else if(t.depthBuffer&&t.storeMultisampledDepthBuffer===!1&&c){let n=t.stencilBuffer?e.DEPTH_STENCIL_ATTACHMENT:e.DEPTH_ATTACHMENT;e.invalidateFramebuffer(e.DRAW_FRAMEBUFFER,[n])}}}function ye(e){return Math.min(i.maxSamples,e.samples)}function R(e){let n=r.get(e);return e.samples>0&&t.has(`WEBGL_multisampled_render_to_texture`)===!0&&n.__useRenderToTexture!==!1}function be(e){let t=o.render.frame;u.get(e)!==t&&(u.set(e,t),e.update())}function xe(e,t){let n=e.colorSpace,r=e.format,i=e.type;return e.isCompressedTexture===!0||e.isVideoTexture===!0||n!==`srgb-linear`&&n!==``&&(vs.getTransfer(n)===`srgb`?(r!==1023||i!==1009)&&K(`WebGLTextures: sRGB encoded textures have to use RGBAFormat and UnsignedByteType.`):q(`WebGLTextures: Unsupported texture color space:`,n)),t}function Se(e){return typeof HTMLImageElement<`u`&&e instanceof HTMLImageElement?(l.width=e.naturalWidth||e.width,l.height=e.naturalHeight||e.height):typeof VideoFrame<`u`&&e instanceof VideoFrame?(l.width=e.displayWidth,l.height=e.displayHeight):(l.width=e.width,l.height=e.height),l}this.allocateTextureUnit=M,this.resetTextureUnits=k,this.getTextureUnits=A,this.setTextureUnits=j,this.setTexture2D=P,this.setTexture2DArray=F,this.setTexture3D=ee,this.setTextureCube=te,this.rebindTextures=pe,this.setupRenderTarget=me,this.updateRenderTargetMipmap=he,this.updateMultisampleRenderTarget=ve,this.setupDepthRenderbuffer=fe,this.setupFrameBufferTexture=le,this.useMultisampledRTT=R,this.isReversedDepthBuffer=function(){return n.buffers.depth.getReversed()}}function Ah(e,t){function n(n,r=``){let i,a=vs.getTransfer(r);if(n===1009)return e.UNSIGNED_BYTE;if(n===1017)return e.UNSIGNED_SHORT_4_4_4_4;if(n===1018)return e.UNSIGNED_SHORT_5_5_5_1;if(n===35902)return e.UNSIGNED_INT_5_9_9_9_REV;if(n===35899)return e.UNSIGNED_INT_10F_11F_11F_REV;if(n===1010)return e.BYTE;if(n===1011)return e.SHORT;if(n===1012)return e.UNSIGNED_SHORT;if(n===1013)return e.INT;if(n===1014)return e.UNSIGNED_INT;if(n===1015)return e.FLOAT;if(n===1016)return e.HALF_FLOAT;if(n===1021)return e.ALPHA;if(n===1022)return e.RGB;if(n===1023)return e.RGBA;if(n===1026)return e.DEPTH_COMPONENT;if(n===1027)return e.DEPTH_STENCIL;if(n===1028)return e.RED;if(n===1029)return e.RED_INTEGER;if(n===1030)return e.RG;if(n===1031)return e.RG_INTEGER;if(n===1033)return e.RGBA_INTEGER;if(n===33776||n===33777||n===33778||n===33779){if(a===`srgb`){if(i=t.get(`WEBGL_compressed_texture_s3tc_srgb`),i!==null){if(n===33776)return i.COMPRESSED_SRGB_S3TC_DXT1_EXT;if(n===33777)return i.COMPRESSED_SRGB_ALPHA_S3TC_DXT1_EXT;if(n===33778)return i.COMPRESSED_SRGB_ALPHA_S3TC_DXT3_EXT;if(n===33779)return i.COMPRESSED_SRGB_ALPHA_S3TC_DXT5_EXT}else return null}else if(i=t.get(`WEBGL_compressed_texture_s3tc`),i!==null){if(n===33776)return i.COMPRESSED_RGB_S3TC_DXT1_EXT;if(n===33777)return i.COMPRESSED_RGBA_S3TC_DXT1_EXT;if(n===33778)return i.COMPRESSED_RGBA_S3TC_DXT3_EXT;if(n===33779)return i.COMPRESSED_RGBA_S3TC_DXT5_EXT}else return null}if(n===35840||n===35841||n===35842||n===35843){if(i=t.get(`WEBGL_compressed_texture_pvrtc`),i!==null){if(n===35840)return i.COMPRESSED_RGB_PVRTC_4BPPV1_IMG;if(n===35841)return i.COMPRESSED_RGB_PVRTC_2BPPV1_IMG;if(n===35842)return i.COMPRESSED_RGBA_PVRTC_4BPPV1_IMG;if(n===35843)return i.COMPRESSED_RGBA_PVRTC_2BPPV1_IMG}else return null}if(n===36196||n===37492||n===37496||n===37488||n===37489||n===37490||n===37491){if(i=t.get(`WEBGL_compressed_texture_etc`),i!==null){if(n===36196||n===37492)return a===`srgb`?i.COMPRESSED_SRGB8_ETC2:i.COMPRESSED_RGB8_ETC2;if(n===37496)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ETC2_EAC:i.COMPRESSED_RGBA8_ETC2_EAC;if(n===37488)return i.COMPRESSED_R11_EAC;if(n===37489)return i.COMPRESSED_SIGNED_R11_EAC;if(n===37490)return i.COMPRESSED_RG11_EAC;if(n===37491)return i.COMPRESSED_SIGNED_RG11_EAC}else return null}if(n===37808||n===37809||n===37810||n===37811||n===37812||n===37813||n===37814||n===37815||n===37816||n===37817||n===37818||n===37819||n===37820||n===37821){if(i=t.get(`WEBGL_compressed_texture_astc`),i!==null){if(n===37808)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_4x4_KHR:i.COMPRESSED_RGBA_ASTC_4x4_KHR;if(n===37809)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_5x4_KHR:i.COMPRESSED_RGBA_ASTC_5x4_KHR;if(n===37810)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_5x5_KHR:i.COMPRESSED_RGBA_ASTC_5x5_KHR;if(n===37811)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_6x5_KHR:i.COMPRESSED_RGBA_ASTC_6x5_KHR;if(n===37812)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_6x6_KHR:i.COMPRESSED_RGBA_ASTC_6x6_KHR;if(n===37813)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_8x5_KHR:i.COMPRESSED_RGBA_ASTC_8x5_KHR;if(n===37814)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_8x6_KHR:i.COMPRESSED_RGBA_ASTC_8x6_KHR;if(n===37815)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_8x8_KHR:i.COMPRESSED_RGBA_ASTC_8x8_KHR;if(n===37816)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_10x5_KHR:i.COMPRESSED_RGBA_ASTC_10x5_KHR;if(n===37817)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_10x6_KHR:i.COMPRESSED_RGBA_ASTC_10x6_KHR;if(n===37818)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_10x8_KHR:i.COMPRESSED_RGBA_ASTC_10x8_KHR;if(n===37819)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_10x10_KHR:i.COMPRESSED_RGBA_ASTC_10x10_KHR;if(n===37820)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_12x10_KHR:i.COMPRESSED_RGBA_ASTC_12x10_KHR;if(n===37821)return a===`srgb`?i.COMPRESSED_SRGB8_ALPHA8_ASTC_12x12_KHR:i.COMPRESSED_RGBA_ASTC_12x12_KHR}else return null}if(n===36492||n===36494||n===36495){if(i=t.get(`EXT_texture_compression_bptc`),i!==null){if(n===36492)return a===`srgb`?i.COMPRESSED_SRGB_ALPHA_BPTC_UNORM_EXT:i.COMPRESSED_RGBA_BPTC_UNORM_EXT;if(n===36494)return i.COMPRESSED_RGB_BPTC_SIGNED_FLOAT_EXT;if(n===36495)return i.COMPRESSED_RGB_BPTC_UNSIGNED_FLOAT_EXT}else return null}if(n===36283||n===36284||n===36285||n===36286){if(i=t.get(`EXT_texture_compression_rgtc`),i!==null){if(n===36283)return i.COMPRESSED_RED_RGTC1_EXT;if(n===36284)return i.COMPRESSED_SIGNED_RED_RGTC1_EXT;if(n===36285)return i.COMPRESSED_RED_GREEN_RGTC2_EXT;if(n===36286)return i.COMPRESSED_SIGNED_RED_GREEN_RGTC2_EXT}else return null}return n===1020?e.UNSIGNED_INT_24_8:e[n]===void 0?null:e[n]}return{convert:n}}var jh=`
void main() {

	gl_Position = vec4( position, 1.0 );

}`,Mh=`
uniform sampler2DArray depthColor;
uniform float depthWidth;
uniform float depthHeight;

void main() {

	vec2 coord = vec2( gl_FragCoord.x / depthWidth, gl_FragCoord.y / depthHeight );

	if ( coord.x >= 1.0 ) {

		gl_FragDepth = texture( depthColor, vec3( coord.x - 1.0, coord.y, 1 ) ).r;

	} else {

		gl_FragDepth = texture( depthColor, vec3( coord.x, coord.y, 0 ) ).r;

	}

}`,Nh=class{constructor(){this.texture=null,this.mesh=null,this.depthNear=0,this.depthFar=0}init(e,t){if(this.texture===null){let n=new hu(e.texture);(e.depthNear!==t.depthNear||e.depthFar!==t.depthFar)&&(this.depthNear=e.depthNear,this.depthFar=e.depthFar),this.texture=n}}getMesh(e){if(this.texture!==null&&this.mesh===null){let t=e.cameras[0].viewport,n=new rd({vertexShader:jh,fragmentShader:Mh,uniforms:{depthColor:{value:this.texture},depthWidth:{value:t.z},depthHeight:{value:t.w}}});this.mesh=new Ll(new Wu(20,20),n)}return this.mesh}reset(){this.texture=null,this.mesh=null}getDepthTexture(){return this.texture}},Ph=class extends Ro{constructor(e,t){super();let n=this,r=null,i=1,a=null,o=`local-floor`,s=1,c=null,l=null,u=null,d=null,f=null,p=null,m=typeof XRWebGLBinding<`u`,h=new Nh,g={},_=t.getContextAttributes(),v=null,y=null,b=[],x=[],S=new Y,C=null,w=null,T=new zd;T.viewport=new ks;let E=new zd;E.viewport=new ks;let D=[T,E],O=new Jd,k=null,A=null;this.cameraAutoUpdate=!0,this.enabled=!1,this.isPresenting=!1,this.getController=function(e){let t=b[e];return t===void 0&&(t=new uc,b[e]=t),t.getTargetRaySpace()},this.getControllerGrip=function(e){let t=b[e];return t===void 0&&(t=new uc,b[e]=t),t.getGripSpace()},this.getHand=function(e){let t=b[e];return t===void 0&&(t=new uc,b[e]=t),t.getHandSpace()};function j(e){let t=x.indexOf(e.inputSource);if(t===-1)return;let n=b[t];n!==void 0&&(n.update(e.inputSource,e.frame,c||a),n.dispatchEvent({type:e.type,data:e.inputSource}))}function M(){r.removeEventListener(`select`,j),r.removeEventListener(`selectstart`,j),r.removeEventListener(`selectend`,j),r.removeEventListener(`squeeze`,j),r.removeEventListener(`squeezestart`,j),r.removeEventListener(`squeezeend`,j),r.removeEventListener(`end`,M),r.removeEventListener(`inputsourceschange`,N);for(let e=0;e<b.length;e++){let t=x[e];t!==null&&(x[e]=null,b[e].disconnect(t))}k=null,A=null,h.reset();for(let e in g)delete g[e];if(e.setRenderTarget(v),f=null,d=null,u=null,r=null,y=null,re.stop(),n.isPresenting=!1,e.setPixelRatio(C),e.setSize(S.width,S.height,!1),w!==null){let e=w.camera;e.fov=w.fov,e.zoom=w.zoom,e.updateProjectionMatrix(),w=null}n.dispatchEvent({type:`sessionend`})}this.setFramebufferScaleFactor=function(e){i=e,n.isPresenting===!0&&K(`WebXRManager: Cannot change framebuffer scale while presenting.`)},this.setReferenceSpaceType=function(e){o=e,n.isPresenting===!0&&K(`WebXRManager: Cannot change reference space type while presenting.`)},this.getReferenceSpace=function(){return c||a},this.setReferenceSpace=function(e){c=e},this.getBaseLayer=function(){return d===null?f:d},this.getBinding=function(){return u===null&&m&&(u=new XRWebGLBinding(r,t)),u},this.getFrame=function(){return p},this.getSession=function(){return r},this.setSession=async function(l){if(r=l,r!==null){if(v=e.getRenderTarget(),r.addEventListener(`select`,j),r.addEventListener(`selectstart`,j),r.addEventListener(`selectend`,j),r.addEventListener(`squeeze`,j),r.addEventListener(`squeezestart`,j),r.addEventListener(`squeezeend`,j),r.addEventListener(`end`,M),r.addEventListener(`inputsourceschange`,N),_.xrCompatible!==!0&&await t.makeXRCompatible(),C=e.getPixelRatio(),e.getSize(S),m&&`createProjectionLayer`in XRWebGLBinding.prototype){let n=null,a=null,o=null;_.depth&&(o=_.stencil?t.DEPTH24_STENCIL8:t.DEPTH_COMPONENT24,n=_.stencil?wa:Ca,a=_.stencil?_a:fa);let s={colorFormat:t.RGBA8,depthFormat:o,scaleFactor:i};u=this.getBinding(),d=u.createProjectionLayer(s),r.updateRenderState({layers:[d]}),e.setPixelRatio(1),e.setSize(d.textureWidth,d.textureHeight,!1),y=new js(d.textureWidth,d.textureHeight,{format:Sa,type:sa,depthTexture:new pu(d.textureWidth,d.textureHeight,a,void 0,void 0,void 0,void 0,void 0,void 0,n),stencilBuffer:_.stencil,colorSpace:e.outputColorSpace,samples:_.antialias?4:0,resolveDepthBuffer:d.ignoreDepthValues===!1,resolveStencilBuffer:d.ignoreDepthValues===!1,storeMultisampledDepthBuffer:d.ignoreDepthValues===!1,storeMultisampledStencilBuffer:d.ignoreDepthValues===!1})}else{let n={antialias:_.antialias,alpha:!0,depth:_.depth,stencil:_.stencil,framebufferScaleFactor:i};f=new XRWebGLLayer(r,t,n),r.updateRenderState({baseLayer:f}),e.setPixelRatio(1),e.setSize(f.framebufferWidth,f.framebufferHeight,!1),y=new js(f.framebufferWidth,f.framebufferHeight,{format:Sa,type:sa,colorSpace:e.outputColorSpace,stencilBuffer:_.stencil,resolveDepthBuffer:f.ignoreDepthValues===!1,resolveStencilBuffer:f.ignoreDepthValues===!1,storeMultisampledDepthBuffer:f.ignoreDepthValues===!1,storeMultisampledStencilBuffer:f.ignoreDepthValues===!1})}y.isXRRenderTarget=!0,this.setFoveation(s),c=null,a=await r.requestReferenceSpace(o),re.setContext(r),re.start(),n.isPresenting=!0,n.dispatchEvent({type:`sessionstart`})}},this.getEnvironmentBlendMode=function(){if(r!==null)return r.environmentBlendMode},this.getDepthTexture=function(){return h.getDepthTexture()};function N(e){for(let t=0;t<e.removed.length;t++){let n=e.removed[t],r=x.indexOf(n);r>=0&&(x[r]=null,b[r].disconnect(n))}for(let t=0;t<e.added.length;t++){let n=e.added[t],r=x.indexOf(n);if(r===-1){for(let e=0;e<b.length;e++)if(e>=x.length){x.push(n),r=e;break}else if(x[e]===null){x[e]=n,r=e;break}if(r===-1)break}let i=b[r];i&&i.connect(n)}}let P=new X,F=new X;function ee(e,t,n){P.setFromMatrixPosition(t.matrixWorld),F.setFromMatrixPosition(n.matrixWorld);let r=P.distanceTo(F),i=t.projectionMatrix.elements,a=n.projectionMatrix.elements,o=i[14]/(i[10]-1),s=i[14]/(i[10]+1),c=(i[9]+1)/i[5],l=(i[9]-1)/i[5],u=(i[8]-1)/i[0],d=(a[8]+1)/a[0],f=o*u,p=o*d,m=r/(-u+d),h=m*-u;if(t.matrixWorld.decompose(e.position,e.quaternion,e.scale),e.translateX(h),e.translateZ(m),e.matrixWorld.compose(e.position,e.quaternion,e.scale),e.matrixWorldInverse.copy(e.matrixWorld).invert(),i[10]===-1)e.projectionMatrix.copy(t.projectionMatrix),e.projectionMatrixInverse.copy(t.projectionMatrixInverse);else{let t=o+m,n=s+m,i=f-h,a=p+(r-h),u=c*s/n*t,d=l*s/n*t;e.projectionMatrix.makePerspective(i,a,u,d,t,n),e.projectionMatrixInverse.copy(e.projectionMatrix).invert()}}function te(e,t){t===null?e.matrixWorld.copy(e.matrix):e.matrixWorld.multiplyMatrices(t.matrixWorld,e.matrix),e.matrixWorldInverse.copy(e.matrixWorld).invert()}this.updateCamera=function(e){if(r===null)return;let t=e.near,n=e.far;h.texture!==null&&(h.depthNear>0&&(t=h.depthNear),h.depthFar>0&&(n=h.depthFar)),O.near=E.near=T.near=t,O.far=E.far=T.far=n,(k!==O.near||A!==O.far)&&(r.updateRenderState({depthNear:O.near,depthFar:O.far}),k=O.near,A=O.far),O.layers.mask=e.layers.mask|6,T.layers.mask=O.layers.mask&-5,E.layers.mask=O.layers.mask&-3;let i=e.parent,a=O.cameras;te(O,i);for(let e=0;e<a.length;e++)te(a[e],i);a.length===2?ee(O,T,E):O.projectionMatrix.copy(T.projectionMatrix),w===null&&e.isPerspectiveCamera&&(w={camera:e,fov:e.fov,zoom:e.zoom}),I(e,O,i)};function I(e,t,n){n===null?e.matrix.copy(t.matrixWorld):(e.matrix.copy(n.matrixWorld),e.matrix.invert(),e.matrix.multiply(t.matrixWorld)),e.matrix.decompose(e.position,e.quaternion,e.scale),e.updateMatrixWorld(!0),e.projectionMatrix.copy(t.projectionMatrix),e.projectionMatrixInverse.copy(t.projectionMatrixInverse),e.isPerspectiveCamera&&(e.fov=Ho*2*Math.atan(1/e.projectionMatrix.elements[5]),e.zoom=1)}this.getCamera=function(){return O},this.getFoveation=function(){if(d!==null||f!==null)return s},this.setFoveation=function(e){s=e,d!==null&&(d.fixedFoveation=e),f!==null&&f.fixedFoveation!==void 0&&(f.fixedFoveation=e)},this.hasDepthSensing=function(){return h.texture!==null},this.getDepthSensingMesh=function(){return h.getMesh(O)},this.getCameraTexture=function(e){return g[e]};let L=null;function ne(t,i){if(l=i.getViewerPose(c||a),p=i,l!==null){let t=l.views;f!==null&&(e.setRenderTargetFramebuffer(y,f.framebuffer),e.setRenderTarget(y));let i=!1;t.length!==O.cameras.length&&(O.cameras.length=0,i=!0);for(let n=0;n<t.length;n++){let r=t[n],a=null;if(f!==null)a=f.getViewport(r);else{let t=u.getViewSubImage(d,r);a=t.viewport,n===0&&(e.setRenderTargetTextures(y,t.colorTexture,t.depthStencilTexture),e.setRenderTarget(y))}let o=D[n];o===void 0&&(o=new zd,o.layers.enable(n),o.viewport=new ks,D[n]=o),o.matrix.fromArray(r.transform.matrix),o.matrix.decompose(o.position,o.quaternion,o.scale),o.projectionMatrix.fromArray(r.projectionMatrix),o.projectionMatrixInverse.copy(o.projectionMatrix).invert(),o.viewport.set(a.x,a.y,a.width,a.height),n===0&&(O.matrix.copy(o.matrix),O.matrix.decompose(O.position,O.quaternion,O.scale)),i===!0&&O.cameras.push(o)}let a=r.enabledFeatures;if(a&&a.includes(`depth-sensing`)&&r.depthUsage==`gpu-optimized`&&m){u=n.getBinding();let e=u.getDepthInformation(t[0]);e&&e.isValid&&e.texture&&h.init(e,r.renderState)}if(a&&a.includes(`camera-access`)&&m){e.state.unbindTexture(),u=n.getBinding();for(let e=0;e<t.length;e++){let n=t[e].camera;if(n){let e=g[n];e||(e=new hu,g[n]=e);let t=u.getCameraImage(n);e.sourceTexture=t}}}}for(let e=0;e<b.length;e++){let t=x[e],n=b[e];t!==null&&n!==void 0&&n.update(t,i,c||a)}L&&L(t,i),i.detectedPlanes&&n.dispatchEvent({type:`planesdetected`,data:i}),p=null}let re=new Tf;re.setAnimationLoop(ne),this.setAnimationLoop=function(e){L=e},this.dispose=function(){}}},Fh=new Ps,Ih=new Z;Ih.set(-1,0,0,0,1,0,0,0,1);function Lh(e,t){function n(e,t){e.matrixAutoUpdate===!0&&e.updateMatrix(),t.value.copy(e.matrix)}function r(t,n){n.color.getRGB(t.fogColor.value,$u(e)),n.isFog?(t.fogNear.value=n.near,t.fogFar.value=n.far):n.isFogExp2&&(t.fogDensity.value=n.density)}function i(e,t,n,r,i){t.isNodeMaterial?t.uniformsNeedUpdate=!1:t.isMeshBasicMaterial?a(e,t):t.isMeshLambertMaterial?(a(e,t),t.envMap&&(e.envMapIntensity.value=t.envMapIntensity)):t.isMeshToonMaterial?(a(e,t),d(e,t)):t.isMeshPhongMaterial?(a(e,t),u(e,t),t.envMap&&(e.envMapIntensity.value=t.envMapIntensity)):t.isMeshStandardMaterial?(a(e,t),f(e,t),t.isMeshPhysicalMaterial&&p(e,t,i)):t.isMeshMatcapMaterial?(a(e,t),m(e,t)):t.isMeshDepthMaterial?a(e,t):t.isMeshDistanceMaterial?(a(e,t),h(e,t)):t.isMeshNormalMaterial?a(e,t):t.isLineBasicMaterial?(o(e,t),t.isLineDashedMaterial&&s(e,t)):t.isPointsMaterial?c(e,t,n,r):t.isSpriteMaterial?l(e,t):t.isShadowMaterial?(e.color.value.copy(t.color),e.opacity.value=t.opacity):t.isShaderMaterial&&(t.uniformsNeedUpdate=!1)}function a(e,r){e.opacity.value=r.opacity,r.color&&e.diffuse.value.copy(r.color),r.emissive&&e.emissive.value.copy(r.emissive).multiplyScalar(r.emissiveIntensity),r.map&&(e.map.value=r.map,n(r.map,e.mapTransform)),r.alphaMap&&(e.alphaMap.value=r.alphaMap,n(r.alphaMap,e.alphaMapTransform)),r.bumpMap&&(e.bumpMap.value=r.bumpMap,n(r.bumpMap,e.bumpMapTransform),e.bumpScale.value=r.bumpScale,r.side===1&&(e.bumpScale.value*=-1)),r.normalMap&&(e.normalMap.value=r.normalMap,n(r.normalMap,e.normalMapTransform),e.normalScale.value.copy(r.normalScale),r.side===1&&e.normalScale.value.negate()),r.displacementMap&&(e.displacementMap.value=r.displacementMap,n(r.displacementMap,e.displacementMapTransform),e.displacementScale.value=r.displacementScale,e.displacementBias.value=r.displacementBias),r.emissiveMap&&(e.emissiveMap.value=r.emissiveMap,n(r.emissiveMap,e.emissiveMapTransform)),r.specularMap&&(e.specularMap.value=r.specularMap,n(r.specularMap,e.specularMapTransform)),r.alphaTest>0&&(e.alphaTest.value=r.alphaTest);let i=t.get(r),a=i.envMap,o=i.envMapRotation;a&&(e.envMap.value=a,e.envMapRotation.value.setFromMatrix4(Fh.makeRotationFromEuler(o)).transpose(),a.isCubeTexture&&a.isRenderTargetTexture===!1&&e.envMapRotation.value.premultiply(Ih),e.reflectivity.value=r.reflectivity,e.ior.value=r.ior,e.refractionRatio.value=r.refractionRatio),r.lightMap&&(e.lightMap.value=r.lightMap,e.lightMapIntensity.value=r.lightMapIntensity,n(r.lightMap,e.lightMapTransform)),r.aoMap&&(e.aoMap.value=r.aoMap,e.aoMapIntensity.value=r.aoMapIntensity,n(r.aoMap,e.aoMapTransform))}function o(e,t){e.diffuse.value.copy(t.color),e.opacity.value=t.opacity,t.map&&(e.map.value=t.map,n(t.map,e.mapTransform))}function s(e,t){e.dashSize.value=t.dashSize,e.totalSize.value=t.dashSize+t.gapSize,e.scale.value=t.scale}function c(e,t,r,i){e.diffuse.value.copy(t.color),e.opacity.value=t.opacity,e.size.value=t.size*r,e.scale.value=i*.5,t.map&&(e.map.value=t.map,n(t.map,e.uvTransform)),t.alphaMap&&(e.alphaMap.value=t.alphaMap,n(t.alphaMap,e.alphaMapTransform)),t.alphaTest>0&&(e.alphaTest.value=t.alphaTest)}function l(e,t){e.diffuse.value.copy(t.color),e.opacity.value=t.opacity,e.rotation.value=t.rotation,t.map&&(e.map.value=t.map,n(t.map,e.mapTransform)),t.alphaMap&&(e.alphaMap.value=t.alphaMap,n(t.alphaMap,e.alphaMapTransform)),t.alphaTest>0&&(e.alphaTest.value=t.alphaTest)}function u(e,t){e.specular.value.copy(t.specular),e.shininess.value=Math.max(t.shininess,1e-4)}function d(e,t){t.gradientMap&&(e.gradientMap.value=t.gradientMap)}function f(e,t){e.metalness.value=t.metalness,t.metalnessMap&&(e.metalnessMap.value=t.metalnessMap,n(t.metalnessMap,e.metalnessMapTransform)),e.roughness.value=t.roughness,t.roughnessMap&&(e.roughnessMap.value=t.roughnessMap,n(t.roughnessMap,e.roughnessMapTransform)),t.envMap&&(e.envMapIntensity.value=t.envMapIntensity)}function p(e,t,r){e.ior.value=t.ior,t.sheen>0&&(e.sheenColor.value.copy(t.sheenColor).multiplyScalar(t.sheen),e.sheenRoughness.value=t.sheenRoughness,t.sheenColorMap&&(e.sheenColorMap.value=t.sheenColorMap,n(t.sheenColorMap,e.sheenColorMapTransform)),t.sheenRoughnessMap&&(e.sheenRoughnessMap.value=t.sheenRoughnessMap,n(t.sheenRoughnessMap,e.sheenRoughnessMapTransform))),t.clearcoat>0&&(e.clearcoat.value=t.clearcoat,e.clearcoatRoughness.value=t.clearcoatRoughness,t.clearcoatMap&&(e.clearcoatMap.value=t.clearcoatMap,n(t.clearcoatMap,e.clearcoatMapTransform)),t.clearcoatRoughnessMap&&(e.clearcoatRoughnessMap.value=t.clearcoatRoughnessMap,n(t.clearcoatRoughnessMap,e.clearcoatRoughnessMapTransform)),t.clearcoatNormalMap&&(e.clearcoatNormalMap.value=t.clearcoatNormalMap,n(t.clearcoatNormalMap,e.clearcoatNormalMapTransform),e.clearcoatNormalScale.value.copy(t.clearcoatNormalScale),t.side===1&&e.clearcoatNormalScale.value.negate())),t.dispersion>0&&(e.dispersion.value=t.dispersion),t.retroreflectivity>0&&(e.retroreflectivity.value=t.retroreflectivity),t.iridescence>0&&(e.iridescence.value=t.iridescence,e.iridescenceIOR.value=t.iridescenceIOR,e.iridescenceThicknessMinimum.value=t.iridescenceThicknessRange[0],e.iridescenceThicknessMaximum.value=t.iridescenceThicknessRange[1],t.iridescenceMap&&(e.iridescenceMap.value=t.iridescenceMap,n(t.iridescenceMap,e.iridescenceMapTransform)),t.iridescenceThicknessMap&&(e.iridescenceThicknessMap.value=t.iridescenceThicknessMap,n(t.iridescenceThicknessMap,e.iridescenceThicknessMapTransform))),t.transmission>0&&(e.transmission.value=t.transmission,e.transmissionSamplerMap.value=r.texture,e.transmissionSamplerSize.value.set(r.width,r.height),t.transmissionMap&&(e.transmissionMap.value=t.transmissionMap,n(t.transmissionMap,e.transmissionMapTransform)),e.thickness.value=t.thickness,t.thicknessMap&&(e.thicknessMap.value=t.thicknessMap,n(t.thicknessMap,e.thicknessMapTransform)),e.attenuationDistance.value=t.attenuationDistance,e.attenuationColor.value.copy(t.attenuationColor)),t.anisotropy>0&&(e.anisotropyVector.value.set(t.anisotropy*Math.cos(t.anisotropyRotation),t.anisotropy*Math.sin(t.anisotropyRotation)),t.anisotropyMap&&(e.anisotropyMap.value=t.anisotropyMap,n(t.anisotropyMap,e.anisotropyMapTransform))),e.specularIntensity.value=t.specularIntensity,e.specularColor.value.copy(t.specularColor),t.specularColorMap&&(e.specularColorMap.value=t.specularColorMap,n(t.specularColorMap,e.specularColorMapTransform)),t.specularIntensityMap&&(e.specularIntensityMap.value=t.specularIntensityMap,n(t.specularIntensityMap,e.specularIntensityMapTransform))}function m(e,t){t.matcap&&(e.matcap.value=t.matcap)}function h(e,n){let r=t.get(n).light;e.referencePosition.value.setFromMatrixPosition(r.matrixWorld),e.nearDistance.value=r.shadow.camera.near,e.farDistance.value=r.shadow.camera.far}return{refreshFogUniforms:r,refreshMaterialUniforms:i}}function Rh(e,t,n,r){let i={},a={},o=[],s=e.getParameter(e.MAX_UNIFORM_BUFFER_BINDINGS);function c(e,t){let n=t.program;r.uniformBlockBinding(e,n)}function l(e,n){let o=i[e.id];o===void 0&&(g(e),o=u(e),i[e.id]=o,e.addEventListener(`dispose`,v));let s=n.program;r.updateUBOMapping(e,s);let c=t.render.frame;a[e.id]!==c&&(f(e),a[e.id]=c)}function u(t){let n=d();t.__bindingPointIndex=n;let r=e.createBuffer(),i=t.__size,a=t.usage;return e.bindBuffer(e.UNIFORM_BUFFER,r),e.bufferData(e.UNIFORM_BUFFER,i,a),e.bindBuffer(e.UNIFORM_BUFFER,null),e.bindBufferBase(e.UNIFORM_BUFFER,n,r),r}function d(){for(let e=0;e<s;e++)if(o.indexOf(e)===-1)return o.push(e),e;return q(`WebGLRenderer: Maximum number of simultaneously usable uniforms groups reached.`),0}function f(t){let n=i[t.id],r=t.uniforms,a=t.__cache;e.bindBuffer(e.UNIFORM_BUFFER,n);for(let e=0,t=r.length;e<t;e++){let t=r[e];if(Array.isArray(t))for(let n=0,r=t.length;n<r;n++)p(t[n],e,n,a);else p(t,e,0,a)}e.bindBuffer(e.UNIFORM_BUFFER,null)}function p(t,n,r,i){if(h(t,n,r,i)===!0){let n=t.__offset,r=t.value;if(Array.isArray(r)){let e=0;for(let n=0;n<r.length;n++){let i=r[n],a=_(i);m(i,t.__data,e),typeof i!=`number`&&typeof i!=`boolean`&&!i.isMatrix3&&!ArrayBuffer.isView(i)&&(e+=a.storage/Float32Array.BYTES_PER_ELEMENT)}}else m(r,t.__data,0);e.bufferSubData(e.UNIFORM_BUFFER,n,t.__data)}}function m(e,t,n){typeof e==`number`||typeof e==`boolean`?t[0]=e:e.isMatrix3?(t[0]=e.elements[0],t[1]=e.elements[1],t[2]=e.elements[2],t[3]=0,t[4]=e.elements[3],t[5]=e.elements[4],t[6]=e.elements[5],t[7]=0,t[8]=e.elements[6],t[9]=e.elements[7],t[10]=e.elements[8],t[11]=0):ArrayBuffer.isView(e)?t.set(new e.constructor(e.buffer,e.byteOffset,t.length)):e.toArray(t,n)}function h(e,t,n,r){let i=e.value,a=t+`_`+n;if(r[a]===void 0)return r[a]=typeof i==`number`||typeof i==`boolean`?i:ArrayBuffer.isView(i)?i.slice():i.clone(),!0;{let e=r[a];if(typeof i==`number`||typeof i==`boolean`){if(e!==i)return r[a]=i,!0}else if(ArrayBuffer.isView(i))return!0;else if(e.equals(i)===!1)return e.copy(i),!0}return!1}function g(e){let t=e.uniforms,n=0;for(let e=0,r=t.length;e<r;e++){let r=Array.isArray(t[e])?t[e]:[t[e]];for(let e=0,t=r.length;e<t;e++){let t=r[e],i=Array.isArray(t.value)?t.value:[t.value];for(let e=0,r=i.length;e<r;e++){let r=i[e],a=_(r),o=n%16,s=o%a.boundary,c=o+s;n+=s,c!==0&&16-c<a.storage&&(n+=16-c),t.__data=new Float32Array(a.storage/Float32Array.BYTES_PER_ELEMENT),t.__offset=n,n+=a.storage}}}let r=n%16;return r>0&&(n+=16-r),e.__size=n,e.__cache={},this}function _(e){let t={boundary:0,storage:0};return typeof e==`number`||typeof e==`boolean`?(t.boundary=4,t.storage=4):e.isVector2?(t.boundary=8,t.storage=8):e.isVector3||e.isColor?(t.boundary=16,t.storage=12):e.isVector4?(t.boundary=16,t.storage=16):e.isMatrix3?(t.boundary=48,t.storage=48):e.isMatrix4?(t.boundary=64,t.storage=64):e.isTexture?K(`WebGLRenderer: Texture samplers can not be part of an uniforms group.`):ArrayBuffer.isView(e)?(t.boundary=16,t.storage=e.byteLength):K(`WebGLRenderer: Unsupported uniform value type.`,e),t}function v(t){let n=t.target;n.removeEventListener(`dispose`,v);let r=o.indexOf(n.__bindingPointIndex);o.splice(r,1),e.deleteBuffer(i[n.id]),delete i[n.id],delete a[n.id]}function y(){for(let t in i)e.deleteBuffer(i[t]);o=[],i={},a={}}return{bind:c,update:l,dispose:y}}var zh=new Uint16Array([12469,15057,12620,14925,13266,14620,13807,14376,14323,13990,14545,13625,14713,13328,14840,12882,14931,12528,14996,12233,15039,11829,15066,11525,15080,11295,15085,10976,15082,10705,15073,10495,13880,14564,13898,14542,13977,14430,14158,14124,14393,13732,14556,13410,14702,12996,14814,12596,14891,12291,14937,11834,14957,11489,14958,11194,14943,10803,14921,10506,14893,10278,14858,9960,14484,14039,14487,14025,14499,13941,14524,13740,14574,13468,14654,13106,14743,12678,14818,12344,14867,11893,14889,11509,14893,11180,14881,10751,14852,10428,14812,10128,14765,9754,14712,9466,14764,13480,14764,13475,14766,13440,14766,13347,14769,13070,14786,12713,14816,12387,14844,11957,14860,11549,14868,11215,14855,10751,14825,10403,14782,10044,14729,9651,14666,9352,14599,9029,14967,12835,14966,12831,14963,12804,14954,12723,14936,12564,14917,12347,14900,11958,14886,11569,14878,11247,14859,10765,14828,10401,14784,10011,14727,9600,14660,9289,14586,8893,14508,8533,15111,12234,15110,12234,15104,12216,15092,12156,15067,12010,15028,11776,14981,11500,14942,11205,14902,10752,14861,10393,14812,9991,14752,9570,14682,9252,14603,8808,14519,8445,14431,8145,15209,11449,15208,11451,15202,11451,15190,11438,15163,11384,15117,11274,15055,10979,14994,10648,14932,10343,14871,9936,14803,9532,14729,9218,14645,8742,14556,8381,14461,8020,14365,7603,15273,10603,15272,10607,15267,10619,15256,10631,15231,10614,15182,10535,15118,10389,15042,10167,14963,9787,14883,9447,14800,9115,14710,8665,14615,8318,14514,7911,14411,7507,14279,7198,15314,9675,15313,9683,15309,9712,15298,9759,15277,9797,15229,9773,15166,9668,15084,9487,14995,9274,14898,8910,14800,8539,14697,8234,14590,7790,14479,7409,14367,7067,14178,6621,15337,8619,15337,8631,15333,8677,15325,8769,15305,8871,15264,8940,15202,8909,15119,8775,15022,8565,14916,8328,14804,8009,14688,7614,14569,7287,14448,6888,14321,6483,14088,6171,15350,7402,15350,7419,15347,7480,15340,7613,15322,7804,15287,7973,15229,8057,15148,8012,15046,7846,14933,7611,14810,7357,14682,7069,14552,6656,14421,6316,14251,5948,14007,5528,15356,5942,15356,5977,15353,6119,15348,6294,15332,6551,15302,6824,15249,7044,15171,7122,15070,7050,14949,6861,14818,6611,14679,6349,14538,6067,14398,5651,14189,5311,13935,4958,15359,4123,15359,4153,15356,4296,15353,4646,15338,5160,15311,5508,15263,5829,15188,6042,15088,6094,14966,6001,14826,5796,14678,5543,14527,5287,14377,4985,14133,4586,13869,4257,15360,1563,15360,1642,15358,2076,15354,2636,15341,3350,15317,4019,15273,4429,15203,4732,15105,4911,14981,4932,14836,4818,14679,4621,14517,4386,14359,4156,14083,3795,13808,3437,15360,122,15360,137,15358,285,15355,636,15344,1274,15322,2177,15281,2765,15215,3223,15120,3451,14995,3569,14846,3567,14681,3466,14511,3305,14344,3121,14037,2800,13753,2467,15360,0,15360,1,15359,21,15355,89,15346,253,15325,479,15287,796,15225,1148,15133,1492,15008,1749,14856,1882,14685,1886,14506,1783,14324,1608,13996,1398,13702,1183]),Bh=null;function Vh(){return Bh===null&&(Bh=new Bl(zh,16,16,Da,ma),Bh.name=`DFG_LUT`,Bh.minFilter=ia,Bh.magFilter=ia,Bh.wrapS=$i,Bh.wrapT=$i,Bh.generateMipmaps=!1,Bh.needsUpdate=!0),Bh}var Hh=class{constructor(e={}){let{canvas:t=jo(),context:n=null,depth:r=!0,stencil:i=!1,alpha:a=!1,antialias:o=!1,premultipliedAlpha:s=!0,preserveDrawingBuffer:c=!1,powerPreference:l=`default`,failIfMajorPerformanceCaveat:u=!1,reversedDepthBuffer:d=!1,outputBufferType:f=sa}=e;this.isWebGLRenderer=!0;let p;if(n!==null){if(typeof WebGLRenderingContext<`u`&&n instanceof WebGLRenderingContext)throw Error(`THREE.WebGLRenderer: WebGL 1 is not supported since r163.`);p=n.getContextAttributes().alpha}else p=a;let m=f,h=new Set([ka,Oa,Ea]),g=new Set([sa,fa,ua,_a,ha,ga]),_=new Uint32Array(4),v=new Int32Array(4),y=new X,b=null,x=null,S=[],C=[],w=null;this.domElement=t,this.debug={checkShaderErrors:!0,diagnostics:{keywords:!1},onShaderError:null},this.autoClear=!0,this.autoClearColor=!0,this.autoClearDepth=!0,this.autoClearStencil=!0,this.sortObjects=!0,this.clippingPlanes=[],this.localClippingEnabled=!1,this.toneMapping=0,this.toneMappingExposure=1,this.transmissionResolutionScale=1;let T=this,E=!1,D=null,O=null,k=null,A=null;this._outputColorSpace=xo;let j=0,M=0,N=null,P=-1,F=null,ee=new ks,te=new ks,I=null,L=new mc(0),ne=0,re=t.width,ie=t.height,ae=1,oe=null,se=null,ce=new ks(0,0,re,ie),le=new ks(0,0,re,ie),ue=!1,de=new Wl,fe=!1,pe=!1,me=new Ps,he=new X,ge=new ks,_e={background:null,fog:null,environment:null,overrideMaterial:null,isScene:!0},ve=!1;function ye(){return N===null?ae:1}let R=n;function be(e,n){return t.getContext(e,n)}let xe,Se,z,Ce,B,V,we,Te,Ee,De,Oe,ke,Ae,je,Me,Ne,Pe,Fe,Ie,Le,Re,ze,Be;try{let e={alpha:!0,depth:r,stencil:i,antialias:o,premultipliedAlpha:s,preserveDrawingBuffer:c,powerPreference:l,failIfMajorPerformanceCaveat:u};if(`setAttribute`in t&&t.setAttribute(`data-engine`,`three.js r186`),t.addEventListener(`webglcontextlost`,Ue,!1),t.addEventListener(`webglcontextrestored`,We,!1),t.addEventListener(`webglcontextcreationerror`,Ge,!1),R===null){let t=`webgl2`;if(R=be(t,e),R===null)throw be(t)?Error(`THREE.WebGLRenderer: Error creating WebGL context with your selected attributes.`):Error(`THREE.WebGLRenderer: Error creating WebGL context.`)}Ve()}catch(e){throw t.removeEventListener(`webglcontextlost`,Ue,!1),t.removeEventListener(`webglcontextrestored`,We,!1),t.removeEventListener(`webglcontextcreationerror`,Ge,!1),q(`WebGLRenderer: `+e.message),e}function Ve(){xe=new op(R),xe.init(),Re=new Ah(R,xe),Se=new Ff(R,xe,e,Re),z=new Oh(R,xe),Se.reversedDepthBuffer&&d&&z.buffers.depth.setReversed(!0),O=R.createFramebuffer(),k=R.createFramebuffer(),A=R.createFramebuffer(),Ce=new lp(R),B=new ch,V=new kh(R,xe,z,B,Se,Re,Ce),we=new ap(T),Te=new Ef(R),ze=new Nf(R,Te),Ee=new sp(R,Te,Ce,ze),De=new dp(R,Ee,Te,ze,Ce),Fe=new up(R,Se,V),Me=new If(B),Oe=new sh(T,we,xe,Se,ze,Me),ke=new Lh(T,B),Ae=new fh,je=new yh(xe),Pe=new Mf(T,we,z,De,p,s),Ne=new Dh(T,De,Se),Be=new Rh(R,Ce,Se,z),Ie=new Pf(R,xe,Ce),Le=new cp(R,xe,Ce),Ce.programs=Oe.programs,T.capabilities=Se,T.extensions=xe,T.properties=B,T.renderLists=Ae,T.shadowMap=Ne,T.state=z,T.info=Ce}m!==1009&&(w=new pp(m,t.width,t.height,o,r,i));let He=new Ph(T,R);this.xr=He,this.getContext=function(){return R},this.getContextAttributes=function(){return R.getContextAttributes()},this.forceContextLoss=function(){let e=xe.get(`WEBGL_lose_context`);e&&e.loseContext()},this.forceContextRestore=function(){let e=xe.get(`WEBGL_lose_context`);e&&e.restoreContext()},this.getPixelRatio=function(){return ae},this.setPixelRatio=function(e){e!==void 0&&(ae=e,this.setSize(re,ie,!1))},this.getSize=function(e){return e.set(re,ie)},this.setSize=function(e,n,r=!0){if(He.isPresenting){K(`WebGLRenderer: Can't change size while VR device is presenting.`);return}re=e,ie=n,t.width=Math.floor(e*ae),t.height=Math.floor(n*ae),r===!0&&(t.style.width=e+`px`,t.style.height=n+`px`),w!==null&&w.setSize(t.width,t.height),this.setViewport(0,0,e,n)},this.getDrawingBufferSize=function(e){return e.set(re*ae,ie*ae).floor()},this.setDrawingBufferSize=function(e,n,r){re=e,ie=n,ae=r,t.width=Math.floor(e*r),t.height=Math.floor(n*r),this.setViewport(0,0,e,n)},this.setEffects=function(e){if(m===1009){q(`WebGLRenderer: setEffects() requires outputBufferType set to HalfFloatType or FloatType.`);return}if(e){for(let t=0;t<e.length;t++)if(e[t].isOutputPass===!0){K(`WebGLRenderer: OutputPass is not needed in setEffects(). Tone mapping and color space conversion are applied automatically.`);break}}w.setEffects(e||[])},this.getCurrentViewport=function(e){return e.copy(ee)},this.getViewport=function(e){return e.copy(ce)},this.setViewport=function(e,t,n,r){e.isVector4?ce.set(e.x,e.y,e.z,e.w):ce.set(e,t,n,r),z.viewport(ee.copy(ce).multiplyScalar(ae).round())},this.getScissor=function(e){return e.copy(le)},this.setScissor=function(e,t,n,r){e.isVector4?le.set(e.x,e.y,e.z,e.w):le.set(e,t,n,r),z.scissor(te.copy(le).multiplyScalar(ae).round())},this.getScissorTest=function(){return ue},this.setScissorTest=function(e){z.setScissorTest(ue=e)},this.setOpaqueSort=function(e){oe=e},this.setTransparentSort=function(e){se=e},this.getClearColor=function(e){return e.copy(Pe.getClearColor())},this.setClearColor=function(){Pe.setClearColor(...arguments)},this.getClearAlpha=function(){return Pe.getClearAlpha()},this.setClearAlpha=function(){Pe.setClearAlpha(...arguments)},this.clear=function(e=!0,t=!0,n=!0){let r=0;if(e){let e=!1;if(N!==null){let t=N.texture.format;e=h.has(t)}if(e){let e=N.texture.type,t=g.has(e),n=Pe.getClearColor(),r=Pe.getClearAlpha(),i=n.r,a=n.g,o=n.b;t?(_[0]=i,_[1]=a,_[2]=o,_[3]=r,R.clearBufferuiv(R.COLOR,0,_)):(v[0]=i,v[1]=a,v[2]=o,v[3]=r,R.clearBufferiv(R.COLOR,0,v))}else r|=R.COLOR_BUFFER_BIT}t&&(r|=R.DEPTH_BUFFER_BIT,this.state.buffers.depth.setMask(!0)),n&&(r|=R.STENCIL_BUFFER_BIT,this.state.buffers.stencil.setMask(4294967295)),r!==0&&R.clear(r)},this.clearColor=function(){this.clear(!0,!1,!1)},this.clearDepth=function(){this.clear(!1,!0,!1)},this.clearStencil=function(){this.clear(!1,!1,!0)},this.setNodesHandler=function(e){e.setRenderer(this),D=e},this.dispose=function(){t.removeEventListener(`webglcontextlost`,Ue,!1),t.removeEventListener(`webglcontextrestored`,We,!1),t.removeEventListener(`webglcontextcreationerror`,Ge,!1),Pe.dispose(),Ae.dispose(),je.dispose(),B.dispose(),we.dispose(),De.dispose(),ze.dispose(),Be.dispose(),Oe.dispose(),He.dispose(),He.removeEventListener(`sessionstart`,Qe),He.removeEventListener(`sessionend`,$e),et.stop()};function Ue(e){e.preventDefault(),No(`WebGLRenderer: Context Lost.`),E=!0}function We(){No(`WebGLRenderer: Context Restored.`),E=!1;let e=Ce.autoReset,t=Ne.enabled,n=Ne.autoUpdate,r=Ne.needsUpdate,i=Ne.type;Ve(),Ce.autoReset=e,Ne.enabled=t,Ne.autoUpdate=n,Ne.needsUpdate=r,Ne.type=i}function Ge(e){q(`WebGLRenderer: A WebGL context could not be created. Reason: `,e.statusMessage)}function Ke(e){let t=e.target;t.removeEventListener(`dispose`,Ke),qe(t)}function qe(e){Je(e),B.remove(e)}function Je(e){let t=B.get(e).programs;t!==void 0&&(t.forEach(function(e){Oe.releaseProgram(e)}),e.isShaderMaterial&&Oe.releaseShaderCache(e))}this.renderBufferDirect=function(e,t,n,r,i,a){t===null&&(t=_e);let o=i.isMesh&&i.matrixWorld.determinantAffine()<0,s=ut(e,t,n,r,i);z.setMaterial(r,o);let c=n.index,l=1;if(r.wireframe===!0){if(c=Ee.getWireframeAttribute(n),c===void 0)return;l=2}let u=n.drawRange,d=n.attributes.position,f=u.start*l,p=(u.start+u.count)*l;a!==null&&(f=Math.max(f,a.start*l),p=Math.min(p,(a.start+a.count)*l)),c===null?d!=null&&(f=Math.max(f,0),p=Math.min(p,d.count)):(f=Math.max(f,0),p=Math.min(p,c.count));let m=p-f;if(m<0||m===1/0)return;ze.setup(i,r,s,n,c);let h,g=Ie;if(c!==null&&(h=Te.get(c),g=Le,g.setIndex(h)),i.isMesh)r.wireframe===!0?(z.setLineWidth(r.wireframeLinewidth*ye()),g.setMode(R.LINES)):g.setMode(R.TRIANGLES);else if(i.isLine){let e=r.linewidth;e===void 0&&(e=1),z.setLineWidth(e*ye()),i.isLineSegments?g.setMode(R.LINES):i.isLineLoop?g.setMode(R.LINE_LOOP):g.setMode(R.LINE_STRIP)}else i.isPoints?g.setMode(R.POINTS):i.isSprite&&g.setMode(R.TRIANGLES);if(i.isBatchedMesh){if(xe.get(`WEBGL_multi_draw`))g.renderMultiDraw(i._multiDrawStarts,i._multiDrawCounts,i._multiDrawCount);else{let e=i._multiDrawStarts,t=i._multiDrawCounts,n=i._multiDrawCount,a=c?Te.get(c).bytesPerElement:1,o=B.get(r).currentProgram.getUniforms();for(let r=0;r<n;r++)o.setValue(R,`_gl_DrawID`,r),g.render(e[r]/a,t[r])}}else if(i.isInstancedMesh)g.renderInstances(f,m,i.count);else if(n.isInstancedBufferGeometry){let e=n._maxInstanceCount===void 0?1/0:n._maxInstanceCount,t=Math.min(n.instanceCount,e);g.renderInstances(f,m,t)}else g.render(f,m)};function Ye(e,t,n,r){D!==null&&e.isNodeMaterial&&D.setObject(r,e),fe===!0&&Me.setState(e,n,!1),e.transparent===!0&&e.side===2&&e.forceSinglePass===!1?(e.side=1,e.needsUpdate=!0,ot(e,t,r),e.side=0,e.needsUpdate=!0,ot(e,t,r),e.side=2):ot(e,t,r)}this.compile=function(e,t,n=null){n===null&&(n=e),D!==null&&D.renderStart(e,t,n),x=je.get(n),x.init(t),C.push(x),n.traverseVisible(function(e){e.isLight&&e.layers.test(t.layers)&&(x.pushLight(e),e.castShadow&&x.pushShadow(e))}),e!==n&&e.traverseVisible(function(e){e.isLight&&e.layers.test(t.layers)&&(x.pushLight(e),e.castShadow&&x.pushShadow(e))}),x.setupLights(),D!==null&&D.updateLights(x.state.lightsArray),pe=this.localClippingEnabled,fe=Me.init(this.clippingPlanes,pe),fe===!0&&Me.setGlobalState(this.clippingPlanes,t),D!==null&&Ne.render(x.state.shadowsArray,n,t);let r=new Set;return e.traverse(function(e){if(!(e.isMesh||e.isPoints||e.isLine||e.isSprite))return;let i=e.material;if(i){if(Array.isArray(i))for(let a=0;a<i.length;a++){let o=i[a];Ye(o,n,t,e),r.add(o)}else Ye(i,n,t,e),r.add(i)}}),x=C.pop(),D!==null&&D.renderEnd(),r},this.compileAsync=function(e,t,n=null){let r=this.compile(e,t,n);return new Promise(t=>{function n(){if(r.forEach(function(e){let t=B.get(e).currentProgram;(t===void 0||t.isReady())&&r.delete(e)}),r.size===0){t(e);return}setTimeout(n,10)}xe.get(`KHR_parallel_shader_compile`)===null?setTimeout(n,10):n()})};let Xe=null;function Ze(e){Xe&&Xe(e)}function Qe(){et.stop()}function $e(){et.start()}let et=new Tf;et.setAnimationLoop(Ze),typeof self<`u`&&et.setContext(self),this.setAnimationLoop=function(e){Xe=e,He.setAnimationLoop(e),e===null?et.stop():et.start()},He.addEventListener(`sessionstart`,Qe),He.addEventListener(`sessionend`,$e),this.render=function(e,t){if(t!==void 0&&t.isCamera!==!0){q(`WebGLRenderer.render: camera is not an instance of THREE.Camera.`);return}if(E===!0)return;D!==null&&D.renderStart(e,t);let n=He.enabled===!0&&He.isPresenting===!0,r=w!==null&&(N===null||n)&&w.begin(T,N);if(e.matrixWorldAutoUpdate===!0&&e.updateMatrixWorld(),t.parent===null&&t.matrixWorldAutoUpdate===!0&&t.updateMatrixWorld(),He.enabled===!0&&He.isPresenting===!0&&(w===null||w.isCompositing()===!1)&&(He.cameraAutoUpdate===!0&&He.updateCamera(t),t=He.getCamera()),e.isScene===!0&&e.onBeforeRender(T,e,t,N),x=je.get(e,C.length),x.init(t),x.state.textureUnits=V.getTextureUnits(),C.push(x),me.multiplyMatrices(t.projectionMatrix,t.matrixWorldInverse),de.setFromProjectionMatrix(me,Do,t.reversedDepth),pe=this.localClippingEnabled,fe=Me.init(this.clippingPlanes,pe),b=Ae.get(e,S.length),b.init(),S.push(b),He.enabled===!0&&He.isPresenting===!0){let e=T.xr.getDepthSensingMesh();e!==null&&tt(e,t,-1/0,T.sortObjects)}tt(e,t,0,T.sortObjects),b.finish(),D!==null&&D.updateLights(x.state.lightsArray),T.sortObjects===!0&&b.sort(oe,se),ve=He.enabled===!1||He.isPresenting===!1||He.hasDepthSensing()===!1,ve&&Pe.addToRenderList(b,e),this.info.render.frame++,this.info.autoReset===!0&&this.info.reset(),fe===!0&&Me.beginShadows();let i=x.state.shadowsArray;if(Ne.render(i,e,t),fe===!0&&Me.endShadows(),(r&&w.hasRenderPass())===!1){let n=b.opaque,r=b.transmissive;if(x.setupLights(),t.isArrayCamera){let i=t.cameras;if(r.length>0)for(let t=0,a=i.length;t<a;t++){let a=i[t];rt(n,r,e,a)}ve&&Pe.render(e);for(let t=0,n=i.length;t<n;t++){let n=i[t];nt(b,e,n,n.viewport)}}else r.length>0&&rt(n,r,e,t),ve&&Pe.render(e),nt(b,e,t)}N!==null&&M===0&&(V.updateMultisampleRenderTarget(N),V.updateRenderTargetMipmap(N)),r&&w.end(T),e.isScene===!0&&e.onAfterRender(T,e,t),ze.resetDefaultState(),P=-1,F=null,C.pop(),C.length>0?(x=C[C.length-1],V.setTextureUnits(x.state.textureUnits),fe===!0&&Me.setGlobalState(T.clippingPlanes,x.state.camera)):x=null,S.pop(),b=S.length>0?S[S.length-1]:null,D!==null&&D.renderEnd()};function tt(e,t,n,r){if(e.visible===!1)return;if(e.layers.test(t.layers)){if(e.isGroup)n=e.renderOrder;else if(e.isLOD)e.autoUpdate===!0&&e.update(t);else if(e.isLightProbeGrid)x.pushLightProbeGrid(e);else if(e.isLight)x.pushLight(e),e.castShadow&&x.pushShadow(e);else if(e.isSprite){if(!e.frustumCulled||e.intersectsFrustum(de)){r&&ge.setFromMatrixPosition(e.matrixWorld).applyMatrix4(me);let i=De.update(e),a=e.material;a.visible&&b.push(e,i,a,n,ge.z,null,t)}}else if((e.isMesh||e.isLine||e.isPoints)&&(!e.frustumCulled||e.intersectsFrustum(de))){let i=De.update(e),a=e.material;if(r&&(e.boundingSphere===void 0?(i.boundingSphere===null&&i.computeBoundingSphere(),ge.copy(i.boundingSphere.center)):(e.boundingSphere===null&&e.computeBoundingSphere(),ge.copy(e.boundingSphere.center)),ge.applyMatrix4(e.matrixWorld).applyMatrix4(me)),Array.isArray(a)){let r=i.groups;for(let o=0,s=r.length;o<s;o++){let s=r[o],c=a[s.materialIndex];c&&c.visible&&b.push(e,i,c,n,ge.z,s,t)}}else a.visible&&b.push(e,i,a,n,ge.z,null,t)}}let i=e.children;for(let e=0,a=i.length;e<a;e++)tt(i[e],t,n,r)}function nt(e,t,n,r){let{opaque:i,transmissive:a,transparent:o}=e;x.setupLightsView(n),fe===!0&&Me.setGlobalState(T.clippingPlanes,n),r&&z.viewport(ee.copy(r)),i.length>0&&it(i,t,n),a.length>0&&it(a,t,n),o.length>0&&it(o,t,n),z.buffers.depth.setTest(!0),z.buffers.depth.setMask(!0),z.buffers.color.setMask(!0),z.setPolygonOffset(!1)}function rt(e,t,n,r){if((n.isScene===!0?n.overrideMaterial:null)!==null)return;if(x.state.transmissionRenderTarget[r.id]===void 0){let e=xe.has(`EXT_color_buffer_half_float`)||xe.has(`EXT_color_buffer_float`);x.state.transmissionRenderTarget[r.id]=new js(1,1,{generateMipmaps:!0,type:e?ma:sa,minFilter:oa,samples:Math.max(4,Se.samples),stencilBuffer:i,resolveDepthBuffer:!1,resolveStencilBuffer:!1,storeMultisampledDepthBuffer:!1,storeMultisampledStencilBuffer:!1,colorSpace:vs.workingColorSpace})}let a=x.state.transmissionRenderTarget[r.id],o=r.viewport||ee;a.setSize(o.z*T.transmissionResolutionScale,o.w*T.transmissionResolutionScale);let s=T.getRenderTarget(),c=T.getActiveCubeFace(),l=T.getActiveMipmapLevel();T.setRenderTarget(a),T.getClearColor(L),ne=T.getClearAlpha(),ne<1&&T.setClearColor(16777215,.5),T.clear(),ve&&Pe.render(n);let u=T.toneMapping;T.toneMapping=0;let d=r.viewport;if(r.viewport!==void 0&&(r.viewport=void 0),x.setupLightsView(r),fe===!0&&Me.setGlobalState(T.clippingPlanes,r),it(e,n,r),V.updateMultisampleRenderTarget(a),V.updateRenderTargetMipmap(a),xe.has(`WEBGL_multisampled_render_to_texture`)===!1){let e=!1;for(let i=0,a=t.length;i<a;i++){let{object:a,geometry:o,material:s,group:c}=t[i];if(s.side===2&&a.layers.test(r.layers)){let t=s.side;s.side=1,s.needsUpdate=!0,at(a,n,r,o,s,c),s.side=t,s.needsUpdate=!0,e=!0}}e===!0&&(V.updateMultisampleRenderTarget(a),V.updateRenderTargetMipmap(a))}T.setRenderTarget(s,c,l),T.setClearColor(L,ne),d!==void 0&&(r.viewport=d),T.toneMapping=u}function it(e,t,n){let r=t.isScene===!0?t.overrideMaterial:null;for(let i=0,a=e.length;i<a;i++){let a=e[i],{object:o,geometry:s,group:c}=a,l=a.material;l.allowOverride===!0&&r!==null&&(l=r),o.layers.test(n.layers)&&at(o,t,n,s,l,c)}}function at(e,t,n,r,i,a){D!==null&&i.isNodeMaterial&&D.setObject(e,i),e.onBeforeRender(T,t,n,r,i,a),e.modelViewMatrix.multiplyMatrices(n.matrixWorldInverse,e.matrixWorld),e.normalMatrix.getNormalMatrix(e.modelViewMatrix),i.onBeforeRender(T,t,n,r,e,a),i.transparent===!0&&i.side===2&&i.forceSinglePass===!1?(i.side=1,i.needsUpdate=!0,T.renderBufferDirect(n,t,r,i,e,a),i.side=0,i.needsUpdate=!0,T.renderBufferDirect(n,t,r,i,e,a),i.side=2):T.renderBufferDirect(n,t,r,i,e,a),e.onAfterRender(T,t,n,r,i,a)}function ot(e,t,n){t.isScene!==!0&&(t=_e);let r=B.get(e),i=x.state.lights,a=x.state.shadowsArray,o=i.state.version,s=Oe.getParameters(e,i.state,a,t,n,x.state.lightProbeGridArray),c=Oe.getProgramCacheKey(s),l=r.programs;r.environment=e.isMeshStandardMaterial||e.isMeshLambertMaterial||e.isMeshPhongMaterial?t.environment:null,r.fog=t.fog;let u=e.isMeshStandardMaterial||e.isMeshLambertMaterial&&!e.envMap||e.isMeshPhongMaterial&&!e.envMap;r.envMap=we.get(e.envMap||r.environment,u),r.envMapRotation=r.environment!==null&&e.envMap===null?t.environmentRotation:e.envMapRotation,l===void 0&&(e.addEventListener(`dispose`,Ke),l=new Map,r.programs=l);let d=l.get(c);if(d!==void 0){if(r.currentProgram===d&&r.lightsStateVersion===o)return ct(e,s),d}else s.uniforms=Oe.getUniforms(e),D!==null&&e.isNodeMaterial&&D.build(e,n,s),e.onBeforeCompile(s,T),d=Oe.acquireProgram(s,c),l.set(c,d),r.uniforms=s.uniforms;let f=r.uniforms;return(!e.isShaderMaterial&&!e.isRawShaderMaterial||e.clipping===!0)&&(f.clippingPlanes=Me.uniform),ct(e,s),r.needsLights=ft(e),r.lightsStateVersion=o,r.needsLights&&(f.ambientLightColor.value=i.state.ambient,f.lightProbe.value=i.state.probe,f.sunLights.value=i.state.sun,f.sunLightShadows.value=i.state.sunShadow,f.directionalLights.value=i.state.directional,f.directionalLightShadows.value=i.state.directionalShadow,f.spotLights.value=i.state.spot,f.spotLightShadows.value=i.state.spotShadow,f.rectAreaLights.value=i.state.rectArea,f.ltc_1.value=i.state.rectAreaLTC1,f.ltc_2.value=i.state.rectAreaLTC2,f.pointLights.value=i.state.point,f.pointLightShadows.value=i.state.pointShadow,f.hemisphereLights.value=i.state.hemi,f.sunShadowMatrix.value=i.state.sunShadowMatrix,f.sunShadowCascade.value=i.state.sunShadowCascade,f.directionalShadowMatrix.value=i.state.directionalShadowMatrix,f.spotLightMatrix.value=i.state.spotLightMatrix,f.spotLightMap.value=i.state.spotLightMap,f.pointShadowMatrix.value=i.state.pointShadowMatrix),r.lightProbeGrid=x.state.lightProbeGridArray.length>0,r.currentProgram=d,r.uniformsList=null,d}function st(e){if(e.uniformsList===null){let t=e.currentProgram.getUniforms();e.uniformsList=bm.seqWithValue(t.seq,e.uniforms)}return e.uniformsList}function ct(e,t){let n=B.get(e);n.outputColorSpace=t.outputColorSpace,n.batching=t.batching,n.batchingColor=t.batchingColor,n.instancing=t.instancing,n.instancingColor=t.instancingColor,n.instancingMorph=t.instancingMorph,n.skinning=t.skinning,n.morphTargets=t.morphTargets,n.morphNormals=t.morphNormals,n.morphColors=t.morphColors,n.morphTargetsCount=t.morphTargetsCount,n.numClippingPlanes=t.numClippingPlanes,n.numIntersection=t.numClipIntersection,n.vertexAlphas=t.vertexAlphas,n.vertexTangents=t.vertexTangents,n.toneMapping=t.toneMapping}function lt(e,t){if(e.length===0)return null;if(e.length===1)return e[0].texture===null?null:e[0];y.setFromMatrixPosition(t.matrixWorld);for(let t=0,n=e.length;t<n;t++){let n=e[t];if(n.texture!==null&&n.boundingBox.containsPoint(y))return n}return null}function ut(e,t,n,r,i){t.isScene!==!0&&(t=_e),V.resetTextureUnits();let a=t.fog,o=r.isMeshStandardMaterial||r.isMeshLambertMaterial||r.isMeshPhongMaterial?t.environment:null,s=N===null?T.outputColorSpace:N.isXRRenderTarget===!0?N.texture.colorSpace:vs.workingColorSpace,c=r.isMeshStandardMaterial||r.isMeshLambertMaterial&&!r.envMap||r.isMeshPhongMaterial&&!r.envMap,l=we.get(r.envMap||o,c),u=r.vertexColors===!0&&!!n.attributes.color&&n.attributes.color.itemSize===4,d=!!n.attributes.tangent&&(!!r.normalMap||r.anisotropy>0),f=!!n.morphAttributes.position,p=!!n.morphAttributes.normal,m=!!n.morphAttributes.color,h=0;r.toneMapped&&(N===null||N.isXRRenderTarget===!0)&&(h=T.toneMapping);let g=n.morphAttributes.position||n.morphAttributes.normal||n.morphAttributes.color,_=g===void 0?0:g.length,v=B.get(r),y=x.state.lights;if(fe===!0&&(pe===!0||e!==F)){let t=e===F&&r.id===P;Me.setState(r,e,t)}let b=!1;r.version===v.__version?v.needsLights&&v.lightsStateVersion!==y.state.version?b=!0:v.outputColorSpace===s?i.isBatchedMesh&&v.batching===!1||!i.isBatchedMesh&&v.batching===!0||i.isBatchedMesh&&v.batchingColor===!0&&i._colorsTexture===null||i.isBatchedMesh&&v.batchingColor===!1&&i._colorsTexture!==null||i.isInstancedMesh&&v.instancing===!1||!i.isInstancedMesh&&v.instancing===!0||i.isSkinnedMesh&&v.skinning===!1||!i.isSkinnedMesh&&v.skinning===!0||i.isInstancedMesh&&v.instancingColor===!0&&i.instanceColor===null||i.isInstancedMesh&&v.instancingColor===!1&&i.instanceColor!==null||i.isInstancedMesh&&v.instancingMorph===!0&&i.morphTexture===null||i.isInstancedMesh&&v.instancingMorph===!1&&i.morphTexture!==null?b=!0:v.envMap===l?r.fog===!0&&v.fog!==a||v.numClippingPlanes!==void 0&&(v.numClippingPlanes!==Me.numPlanes||v.numIntersection!==Me.numIntersection)?b=!0:v.vertexAlphas===u&&v.vertexTangents===d&&v.morphTargets===f&&v.morphNormals===p&&v.morphColors===m&&v.toneMapping===h&&v.morphTargetsCount===_?!!v.lightProbeGrid!=x.state.lightProbeGridArray.length>0&&(b=!0):b=!0:b=!0:b=!0:(b=!0,v.__version=r.version);let S=v.currentProgram;b===!0&&(S=ot(r,t,i),D&&r.isNodeMaterial&&D.onUpdateProgram(r,S,v));let C=!1,w=!1,E=!1,O=S.getUniforms(),k=v.uniforms;if(z.useProgram(S.program)&&(C=!0,w=!0,E=!0),r.id!==P&&(P=r.id,w=!0),v.needsLights){let e=lt(x.state.lightProbeGridArray,i);v.lightProbeGrid!==e&&(v.lightProbeGrid=e,w=!0)}if(C||F!==e){z.buffers.depth.getReversed()&&e.reversedDepth!==!0&&(e._reversedDepth=!0,e.updateProjectionMatrix()),O.setValue(R,`projectionMatrix`,e.projectionMatrix),O.setValue(R,`viewMatrix`,e.matrixWorldInverse);let t=O.map.cameraPosition;t!==void 0&&t.setValue(R,he.setFromMatrixPosition(e.matrixWorld)),Se.logarithmicDepthBuffer&&O.setValue(R,`logDepthBufFC`,2/(Math.log(e.far+1)/Math.LN2)),(r.isMeshPhongMaterial||r.isMeshToonMaterial||r.isMeshLambertMaterial||r.isMeshBasicMaterial||r.isMeshStandardMaterial||r.isShaderMaterial)&&O.setValue(R,`isOrthographic`,e.isOrthographicCamera===!0),F!==e&&(F=e,w=!0,E=!0)}if(v.needsLights&&(y.state.sunShadowMap.length>0&&O.setValue(R,`sunShadowMap`,y.state.sunShadowMap,V),y.state.directionalShadowMap.length>0&&O.setValue(R,`directionalShadowMap`,y.state.directionalShadowMap,V),y.state.spotShadowMap.length>0&&O.setValue(R,`spotShadowMap`,y.state.spotShadowMap,V),y.state.pointShadowMap.length>0&&O.setValue(R,`pointShadowMap`,y.state.pointShadowMap,V)),i.isSkinnedMesh){O.setOptional(R,i,`bindMatrix`),O.setOptional(R,i,`bindMatrixInverse`);let e=i.skeleton;e&&(e.boneTexture===null&&e.computeBoneTexture(),O.setValue(R,`boneTexture`,e.boneTexture,V))}i.isBatchedMesh&&(O.setOptional(R,i,`batchingTexture`),O.setValue(R,`batchingTexture`,i._matricesTexture,V),O.setOptional(R,i,`batchingIdTexture`),O.setValue(R,`batchingIdTexture`,i._indirectTexture,V),O.setOptional(R,i,`batchingColorTexture`),i._colorsTexture!==null&&O.setValue(R,`batchingColorTexture`,i._colorsTexture,V));let A=n.morphAttributes;if((A.position!==void 0||A.normal!==void 0||A.color!==void 0)&&Fe.update(i,n,S),(w||v.receiveShadow!==i.receiveShadow)&&(v.receiveShadow=i.receiveShadow,O.setValue(R,`receiveShadow`,i.receiveShadow)),(r.isMeshStandardMaterial||r.isMeshLambertMaterial||r.isMeshPhongMaterial)&&r.envMap===null&&t.environment!==null&&(k.envMapIntensity.value=t.environmentIntensity),k.dfgLUT!==void 0&&(k.dfgLUT.value=Vh()),w){if(O.setValue(R,`toneMappingExposure`,T.toneMappingExposure),v.needsLights&&dt(k,E),a&&r.fog===!0&&ke.refreshFogUniforms(k,a),ke.refreshMaterialUniforms(k,r,ae,ie,x.state.transmissionRenderTarget[e.id]),v.needsLights&&v.lightProbeGrid){let e=v.lightProbeGrid;k.probesSH.value=e.texture,k.probesMin.value.copy(e.boundingBox.min),k.probesMax.value.copy(e.boundingBox.max),k.probesResolution.value.copy(e.resolution)}bm.upload(R,st(v),k,V)}if(r.isShaderMaterial&&r.uniformsNeedUpdate===!0&&(bm.upload(R,st(v),k,V),r.uniformsNeedUpdate=!1),r.isSpriteMaterial&&O.setValue(R,`center`,i.center),O.setValue(R,`modelViewMatrix`,i.modelViewMatrix),O.setValue(R,`normalMatrix`,i.normalMatrix),O.setValue(R,`modelMatrix`,i.matrixWorld),r.uniformsGroups!==void 0){let e=r.uniformsGroups;for(let t=0,n=e.length;t<n;t++){let n=e[t];Be.update(n,S),Be.bind(n,S)}}return S}function dt(e,t){e.ambientLightColor.needsUpdate=t,e.lightProbe.needsUpdate=t,e.sunLights.needsUpdate=t,e.sunLightShadows.needsUpdate=t,e.directionalLights.needsUpdate=t,e.directionalLightShadows.needsUpdate=t,e.pointLights.needsUpdate=t,e.pointLightShadows.needsUpdate=t,e.spotLights.needsUpdate=t,e.spotLightShadows.needsUpdate=t,e.rectAreaLights.needsUpdate=t,e.hemisphereLights.needsUpdate=t}function ft(e){return e.isMeshLambertMaterial||e.isMeshToonMaterial||e.isMeshPhongMaterial||e.isMeshStandardMaterial||e.isShadowMaterial||e.isShaderMaterial&&e.lights===!0}this.getActiveCubeFace=function(){return j},this.getActiveMipmapLevel=function(){return M},this.getRenderTarget=function(){return N},this.setRenderTargetTextures=function(e,t,n){let r=B.get(e);r.__autoAllocateDepthBuffer=e.resolveDepthBuffer===!1,r.__autoAllocateDepthBuffer===!1&&(r.__useRenderToTexture=!1),B.get(e.texture).__webglTexture=t,B.get(e.depthTexture).__webglTexture=r.__autoAllocateDepthBuffer?void 0:n,r.__hasExternalTextures=!0},this.setRenderTargetFramebuffer=function(e,t){let n=B.get(e);n.__webglFramebuffer=t,n.__useDefaultFramebuffer=t===void 0},this.setRenderTarget=function(e,t=0,n=0){N=e,j=t,M=n;let r=null,i=!1,a=!1;if(e){let o=B.get(e);if(o.__useDefaultFramebuffer!==void 0){z.bindFramebuffer(R.FRAMEBUFFER,o.__webglFramebuffer),ee.copy(e.viewport),te.copy(e.scissor),I=e.scissorTest,z.viewport(ee),z.scissor(te),z.setScissorTest(I),P=-1;return}if(o.__webglFramebuffer===void 0)V.setupRenderTarget(e);else if(o.__hasExternalTextures)V.rebindTextures(e,B.get(e.texture).__webglTexture,B.get(e.depthTexture).__webglTexture);else if(e.depthBuffer){let t=e.depthTexture;if(o.__boundDepthTexture!==t){if(t!==null&&B.has(t)&&(e.width!==t.image.width||e.height!==t.image.height))throw Error(`THREE.WebGLRenderer: Attached DepthTexture is initialized to the incorrect size.`);V.setupDepthRenderbuffer(e)}}let s=e.texture;(s.isData3DTexture||s.isDataArrayTexture||s.isCompressedArrayTexture)&&(a=!0);let c=B.get(e).__webglFramebuffer;e.isWebGLCubeRenderTarget?(r=Array.isArray(c[t])?c[t][n]:c[t],i=!0):r=e.samples>0&&V.useMultisampledRTT(e)===!1?B.get(e).__webglMultisampledFramebuffer:Array.isArray(c)?c[n]:c,ee.copy(e.viewport),te.copy(e.scissor),I=e.scissorTest}else ee.copy(ce).multiplyScalar(ae).floor(),te.copy(le).multiplyScalar(ae).floor(),I=ue;if(n!==0&&(r=O),z.bindFramebuffer(R.FRAMEBUFFER,r)&&z.drawBuffers(e,r),z.viewport(ee),z.scissor(te),z.setScissorTest(I),i){let r=B.get(e.texture);R.framebufferTexture2D(R.FRAMEBUFFER,R.COLOR_ATTACHMENT0,R.TEXTURE_CUBE_MAP_POSITIVE_X+t,r.__webglTexture,n)}else if(a){let r=t;for(let t=0;t<e.textures.length;t++){let i=B.get(e.textures[t]);R.framebufferTextureLayer(R.FRAMEBUFFER,R.COLOR_ATTACHMENT0+t,i.__webglTexture,n,r)}}else if(e!==null&&n!==0){let t=B.get(e.texture);R.framebufferTexture2D(R.FRAMEBUFFER,R.COLOR_ATTACHMENT0,R.TEXTURE_2D,t.__webglTexture,n)}P=-1};function pt(e){let t=B.get(e);return(t.__readFormat!==e.format||t.__readType!==e.type)&&(t.__readFormat=e.format,t.__readType=e.type,t.__formatReadable=Se.textureFormatReadable(e.format),t.__typeReadable=Se.textureTypeReadable(e.type)),t}this.readRenderTargetPixels=function(e,t,n,r,i,a,o,s=0){if(!(e&&e.isWebGLRenderTarget)){q(`WebGLRenderer.readRenderTargetPixels: renderTarget is not THREE.WebGLRenderTarget.`);return}let c=B.get(e).__webglFramebuffer;if(e.isWebGLCubeRenderTarget&&o!==void 0&&(c=c[o]),c){z.bindFramebuffer(R.FRAMEBUFFER,c);try{let o=e.textures[s],c=o.format,l=o.type;e.textures.length>1&&R.readBuffer(R.COLOR_ATTACHMENT0+s);let u=pt(o);if(u.__formatReadable===!1){q(`WebGLRenderer.readRenderTargetPixels: renderTarget is not in RGBA or implementation defined format.`);return}if(u.__typeReadable===!1){q(`WebGLRenderer.readRenderTargetPixels: renderTarget is not in UnsignedByteType or implementation defined type.`);return}t>=0&&t<=e.width-r&&n>=0&&n<=e.height-i&&R.readPixels(t,n,r,i,Re.convert(c),Re.convert(l),a)}finally{let e=N===null?null:B.get(N).__webglFramebuffer;z.bindFramebuffer(R.FRAMEBUFFER,e)}}},this.readRenderTargetPixelsAsync=async function(e,t,n,r,i,a,o,s=0){if(!(e&&e.isWebGLRenderTarget))throw Error(`THREE.WebGLRenderer.readRenderTargetPixels: renderTarget is not THREE.WebGLRenderTarget.`);let c=B.get(e).__webglFramebuffer;if(e.isWebGLCubeRenderTarget&&o!==void 0&&(c=c[o]),c){if(t>=0&&t<=e.width-r&&n>=0&&n<=e.height-i){z.bindFramebuffer(R.FRAMEBUFFER,c);let o=e.textures[s],l=o.format,u=o.type;e.textures.length>1&&R.readBuffer(R.COLOR_ATTACHMENT0+s);let d=pt(o);if(d.__formatReadable===!1)throw Error(`THREE.WebGLRenderer.readRenderTargetPixelsAsync: renderTarget is not in RGBA or implementation defined format.`);if(d.__typeReadable===!1)throw Error(`THREE.WebGLRenderer.readRenderTargetPixelsAsync: renderTarget is not in UnsignedByteType or implementation defined type.`);let f=R.createBuffer();R.bindBuffer(R.PIXEL_PACK_BUFFER,f),R.bufferData(R.PIXEL_PACK_BUFFER,a.byteLength,R.STREAM_READ),R.readPixels(t,n,r,i,Re.convert(l),Re.convert(u),0),R.bindBuffer(R.PIXEL_PACK_BUFFER,null);let p=N===null?null:B.get(N).__webglFramebuffer;z.bindFramebuffer(R.FRAMEBUFFER,p);let m=R.fenceSync(R.SYNC_GPU_COMMANDS_COMPLETE,0);return R.flush(),await Io(R,m,4),R.bindBuffer(R.PIXEL_PACK_BUFFER,f),R.getBufferSubData(R.PIXEL_PACK_BUFFER,0,a),R.bindBuffer(R.PIXEL_PACK_BUFFER,null),R.deleteBuffer(f),R.deleteSync(m),a}throw Error(`THREE.WebGLRenderer.readRenderTargetPixelsAsync: requested read bounds are out of range.`)}},this.copyFramebufferToTexture=function(e,t=null,n=0){let r=2**-n,i=Math.floor(e.image.width*r),a=Math.floor(e.image.height*r),o=t===null?0:t.x,s=t===null?0:t.y;V.setTexture2D(e,0),R.copyTexSubImage2D(R.TEXTURE_2D,n,0,0,o,s,i,a),z.unbindTexture()},this.copyTextureToTexture=function(e,t,n=null,r=null,i=0,a=0){let o,s,c,l,u,d,f,p,m,h=e.isCompressedTexture?e.mipmaps[a]:e.image;if(n!==null)o=n.max.x-n.min.x,s=n.max.y-n.min.y,c=n.isBox3?n.max.z-n.min.z:1,l=n.min.x,u=n.min.y,d=n.isBox3?n.min.z:0;else{let t=2**-i;o=Math.floor(h.width*t),s=Math.floor(h.height*t),c=e.isDataArrayTexture?h.depth:e.isData3DTexture?Math.floor(h.depth*t):1,l=0,u=0,d=0}r===null?(f=0,p=0,m=0):(f=r.x,p=r.y,m=r.z);let g=Re.convert(t.format),_=Re.convert(t.type),v;t.isData3DTexture?(V.setTexture3D(t,0),v=R.TEXTURE_3D):t.isDataArrayTexture||t.isCompressedArrayTexture?(V.setTexture2DArray(t,0),v=R.TEXTURE_2D_ARRAY):(V.setTexture2D(t,0),v=R.TEXTURE_2D),z.activeTexture(R.TEXTURE0),z.pixelStorei(R.UNPACK_FLIP_Y_WEBGL,t.flipY),z.pixelStorei(R.UNPACK_PREMULTIPLY_ALPHA_WEBGL,t.premultiplyAlpha),z.pixelStorei(R.UNPACK_ALIGNMENT,t.unpackAlignment);let y=z.getParameter(R.UNPACK_ROW_LENGTH),b=z.getParameter(R.UNPACK_IMAGE_HEIGHT),x=z.getParameter(R.UNPACK_SKIP_PIXELS),S=z.getParameter(R.UNPACK_SKIP_ROWS),C=z.getParameter(R.UNPACK_SKIP_IMAGES);z.pixelStorei(R.UNPACK_ROW_LENGTH,h.width),z.pixelStorei(R.UNPACK_IMAGE_HEIGHT,h.height),z.pixelStorei(R.UNPACK_SKIP_PIXELS,l),z.pixelStorei(R.UNPACK_SKIP_ROWS,u),z.pixelStorei(R.UNPACK_SKIP_IMAGES,d);let w=e.isDataArrayTexture||e.isData3DTexture,T=t.isDataArrayTexture||t.isData3DTexture;if(e.isDepthTexture){let n=B.get(e),r=B.get(t),h=B.get(n.__renderTarget),g=B.get(r.__renderTarget);z.bindFramebuffer(R.READ_FRAMEBUFFER,h.__webglFramebuffer),z.bindFramebuffer(R.DRAW_FRAMEBUFFER,g.__webglFramebuffer);for(let n=0;n<c;n++)w&&(R.framebufferTextureLayer(R.READ_FRAMEBUFFER,R.COLOR_ATTACHMENT0,B.get(e).__webglTexture,i,d+n),R.framebufferTextureLayer(R.DRAW_FRAMEBUFFER,R.COLOR_ATTACHMENT0,B.get(t).__webglTexture,a,m+n)),R.blitFramebuffer(l,u,o,s,f,p,o,s,R.DEPTH_BUFFER_BIT,R.NEAREST);z.bindFramebuffer(R.READ_FRAMEBUFFER,null),z.bindFramebuffer(R.DRAW_FRAMEBUFFER,null)}else if(i!==0||e.isRenderTargetTexture||B.has(e)){let n=B.get(e),r=B.get(t);z.bindFramebuffer(R.READ_FRAMEBUFFER,k),z.bindFramebuffer(R.DRAW_FRAMEBUFFER,A);for(let e=0;e<c;e++)w?R.framebufferTextureLayer(R.READ_FRAMEBUFFER,R.COLOR_ATTACHMENT0,n.__webglTexture,i,d+e):R.framebufferTexture2D(R.READ_FRAMEBUFFER,R.COLOR_ATTACHMENT0,R.TEXTURE_2D,n.__webglTexture,i),T?R.framebufferTextureLayer(R.DRAW_FRAMEBUFFER,R.COLOR_ATTACHMENT0,r.__webglTexture,a,m+e):R.framebufferTexture2D(R.DRAW_FRAMEBUFFER,R.COLOR_ATTACHMENT0,R.TEXTURE_2D,r.__webglTexture,a),i===0?T?R.copyTexSubImage3D(v,a,f,p,m+e,l,u,o,s):R.copyTexSubImage2D(v,a,f,p,l,u,o,s):R.blitFramebuffer(l,u,o,s,f,p,o,s,R.COLOR_BUFFER_BIT,R.NEAREST);z.bindFramebuffer(R.READ_FRAMEBUFFER,null),z.bindFramebuffer(R.DRAW_FRAMEBUFFER,null)}else T?e.isDataTexture||e.isData3DTexture?R.texSubImage3D(v,a,f,p,m,o,s,c,g,_,h.data):t.isCompressedArrayTexture?R.compressedTexSubImage3D(v,a,f,p,m,o,s,c,g,h.data):R.texSubImage3D(v,a,f,p,m,o,s,c,g,_,h):e.isDataTexture?R.texSubImage2D(R.TEXTURE_2D,a,f,p,o,s,g,_,h.data):e.isCompressedTexture?R.compressedTexSubImage2D(R.TEXTURE_2D,a,f,p,h.width,h.height,g,h.data):R.texSubImage2D(R.TEXTURE_2D,a,f,p,o,s,g,_,h);z.pixelStorei(R.UNPACK_ROW_LENGTH,y),z.pixelStorei(R.UNPACK_IMAGE_HEIGHT,b),z.pixelStorei(R.UNPACK_SKIP_PIXELS,x),z.pixelStorei(R.UNPACK_SKIP_ROWS,S),z.pixelStorei(R.UNPACK_SKIP_IMAGES,C),a===0&&t.generateMipmaps&&R.generateMipmap(v),z.unbindTexture()},this.initRenderTarget=function(e){B.get(e).__webglFramebuffer===void 0&&V.setupRenderTarget(e)},this.initTexture=function(e){e.isCubeTexture?V.setTextureCube(e,0):e.isData3DTexture?V.setTexture3D(e,0):e.isDataArrayTexture||e.isCompressedArrayTexture?V.setTexture2DArray(e,0):V.setTexture2D(e,0),z.unbindTexture()},this.resetState=function(){j=0,M=0,N=null,z.reset(),ze.reset()},typeof __THREE_DEVTOOLS__<`u`&&__THREE_DEVTOOLS__.dispatchEvent(new CustomEvent(`observe`,{detail:this}))}get coordinateSystem(){return Do}get outputColorSpace(){return this._outputColorSpace}set outputColorSpace(e){this._outputColorSpace=e;let t=this.getContext();t.drawingBufferColorSpace=vs._getDrawingBufferColorSpace(e),t.unpackColorSpace=vs._getUnpackColorSpace()}};function Uh(e,t){let{header:n,positions:r,starts:i,offsets:a}=e,o=[],s=0;if(n.segments.forEach((e,n)=>{t(e,n)&&(o.push(n),s+=a[n+1]-a[n])}),o.length===n.segments.length)return e;let c=new Float32Array(3*s),l=new Uint32Array(s),u=new Uint32Array(o.length+1),d=[1/0,1/0,1/0],f=[-1/0,-1/0,-1/0],p=0;return o.forEach((e,t)=>{let n=a[e],o=a[e+1];c.set(r.subarray(3*n,3*o),3*p),l.set(i.subarray(n,o),p);for(let e=n;e<o;e++)for(let t=0;t<3;t++){let n=r[3*e+t];n<d[t]&&(d[t]=n),n>f[t]&&(f[t]=n)}p+=o-n,u[t+1]=p}),{header:{...n,n_points:s,n_segments:o.length,segments:o.map(e=>n.segments[e]),bbox:s?{min:d,max:f}:n.bbox},positions:c,starts:l,offsets:u}}function Wh(e,t){return e===null?!0:t===null?!1:typeof e==`string`?t===e:e.has(t)}function Gh(e,t,n){let r=e=>!t.has(e.chrom);if(n===null){let t=Uh(e,r);return{main:t.header.n_points?t:null,context:null}}let i=Uh(e,e=>r(e)&&Wh(n,e.cell_id)),a=Uh(e,e=>r(e)&&!Wh(n,e.cell_id));return{main:i.header.n_points?i:null,context:a.header.n_points?a:null}}function Kh(e,t,n){let r=[],i=[],a=e.positions;for(let o=0;o<e.n;o++)t.has(e.labels[o])||Number.isFinite(a[3*o])&&Number.isFinite(a[3*o+1])&&Number.isFinite(a[3*o+2])&&(Wh(n,e.cellIds[o])?r.push(o):i.push(o));return{main:Uint32Array.from(r),context:Uint32Array.from(i)}}function qh(e){let t=new Map;for(let n of e.labels)t.set(n,(t.get(n)??0)+1);return[...t].map(([e,t])=>({value:e,count:t})).sort((e,t)=>t.count-e.count||e.value.localeCompare(t.value))}var Jh=null;function Yh(){if(Jh)return Jh;let e=document.createElement(`canvas`);e.width=e.height=64;let t=e.getContext(`2d`);return t.beginPath(),t.arc(32,32,28,0,Math.PI*2),t.fillStyle=`#ffffff`,t.fill(),t.lineWidth=5,t.strokeStyle=`rgba(0,0,0,0.65)`,t.stroke(),Jh=new fu(e),Jh}function Xh(e,t,n,r){let i=new Float32Array(3*t.length),a=new Float32Array(3*t.length),o=P(qh(e).map(e=>e.value)),s=new Map;t.forEach((t,n)=>{i.set(e.positions.subarray(3*t,3*t+3),3*n);let r=e.labels[t],c=s.get(r);c||s.set(r,c=o(r)),a.set(c,3*n)});let c=new ul;c.setAttribute(`position`,new Yc(i,3)),c.setAttribute(`color`,new Yc(ee(a),3)),c.computeBoundingSphere();let l=new iu({size:n,sizeAttenuation:!1,vertexColors:!0,map:Yh(),alphaTest:.5,transparent:r<1,opacity:r,depthWrite:r>=1}),u=new lu(c,l);return u.renderOrder=1,{object:u,indices:t,dispose:()=>{c.dispose(),l.dispose()}}}function Zh(){let e=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)),t=W(e=>e.activeDatasetId?e.pointSets[e.activeDatasetId]:void 0),n=W(U),r=W(e=>e.togglePointSet),i=W(e=>e.toggleLabel),a=W(e=>e.setHiddenLabels),o=W(e=>e.setPointSize),s=e?.point_sets??[];return s.length?(0,G.jsxs)(`section`,{className:`points-panel`,children:[s.map(e=>{let o=t?.[e.name],s=o?qh(o):e.labels,c=new Set(n.hiddenLabels[e.name]??[]),l=n.hiddenPointSets.includes(e.name),u=s.map(e=>e.value),d=P(u);return(0,G.jsxs)(`div`,{children:[(0,G.jsxs)(`h2`,{children:[(0,G.jsxs)(`label`,{className:`check`,children:[(0,G.jsx)(`input`,{type:`checkbox`,checked:!l,onChange:()=>r(e.name)}),` `,e.name,` points`,(0,G.jsxs)(`span`,{className:`muted`,children:[` `,e.n_points.toLocaleString(`en-US`)]})]}),(0,G.jsxs)(`span`,{className:`legend-actions`,children:[(0,G.jsx)(`button`,{onClick:()=>a(e.name,[]),disabled:!c.size,children:`all`}),(0,G.jsx)(`button`,{onClick:()=>a(e.name,u),disabled:c.size===u.length,children:`none`})]})]}),!o&&(0,G.jsx)(`div`,{className:`muted small`,children:`loading…`}),!l&&(0,G.jsx)(`ul`,{className:`legend-list labels`,children:s.map(t=>(0,G.jsxs)(`li`,{className:c.has(t.value)?`off`:``,onClick:()=>i(e.name,t.value),onDoubleClick:()=>a(e.name,u.filter(e=>e!==t.value)),title:`${t.count} spots · click to show/hide · double-click to show only this one`,children:[(0,G.jsx)(`span`,{className:`swatch round`,style:{background:te(d(t.value))}}),(0,G.jsx)(`span`,{className:`name`,children:t.value||`(none)`}),(0,G.jsx)(`span`,{className:`muted count`,children:t.count})]},t.value))})]},e.name)}),(0,G.jsxs)(`label`,{children:[`Marker size `,(0,G.jsxs)(`span`,{className:`val`,children:[n.pointSize,`px`]})]}),(0,G.jsx)(`input`,{type:`range`,min:2,max:16,step:1,value:n.pointSize,onChange:e=>o(+e.target.value)})]}):null}function Qh(e,t){let n=3*t,r=n+3;return Math.hypot(e[r]-e[n],e[r+1]-e[n+1],e[r+2]-e[n+2])}function $h(e){let{positions:t,offsets:n}=e,r=[],i=Math.max(1,Math.floor(t.length/3/2e4));for(let e=0;e+1<n.length;e++)for(let a=n[e];a+1<n[e+1];a+=i){let e=Qh(t,a);e>0&&r.push(e)}return r.length?(r.sort((e,t)=>e-t),r[Math.floor(r.length/2)]):null}function eg(e,t){if(t===null||!(t>0))return{geometry:e,broken:0};let{positions:n,starts:r,offsets:i,header:a}=e,o=[0],s=[],c=0;for(let e=0;e+1<i.length;e++){let l=i[e],u=i[e+1],d=a.segments[e],f=l,p=e=>{let t=1/0,n=-1/0;for(let i=f;i<e;i++)t=Math.min(t,r[i]),n=Math.max(n,r[i]);let i=d.n_points>1?Math.max(0,(d.end-d.start)/d.n_points):d.end-d.start;s.push({...d,n_points:e-f,start:e>f?t:d.start,end:e>f?Math.round(n+i):d.end}),o.push(e),f=e},m=!1;for(let e=l;e+1<u;e++)Qh(n,e)>t&&(c++,m=!0,p(e+1));m?p(u):(s.push(d),o.push(u))}return c?{geometry:{...e,offsets:Uint32Array.from(o),header:{...a,n_segments:s.length,segments:s}},broken:c}:{geometry:e,broken:0}}var tg=new WeakMap;function ng(e,t){if(t===null)return null;if(t===`auto`){let t=$h(e);return t===null?null:t*10}return t}function rg(e,t){let n=ng(e,t),r=tg.get(e);r||tg.set(e,r=new Map);let i=String(n),a=r.get(i);return a||r.set(i,a=eg(e,n)),{...a,threshold:n}}function ig(e){let t=0;for(let n=0;n+1<e.length;n++)t+=Math.max(0,e[n+1]-e[n]-1);let n=new Uint32Array(2*t),r=0;for(let t=0;t+1<e.length;t++)for(let i=e[t];i+1<e[t+1];i++)n[r++]=i,n[r++]=i+1;return n}function ag(e,t){let n=e.length-1;if(n<=0||t<e[0]||t>=e[n])return-1;let r=0,i=n-1;for(;r<i;){let n=r+i+1>>1;e[n]<=t?r=n:i=n-1}return r}function og(e){if(!e)return 0;let t=[0,1,2].map(t=>e.max[t]-e.min[t]);return Math.hypot(t[0],t[1],t[2])}function sg(e){let{positions:t,offsets:n}=e,r=[],i=Math.max(1,Math.floor(t.length/3/2e4));for(let e=0;e+1<n.length;e++)for(let a=n[e];a+1<n[e+1];a+=i){let e=3*a,n=e+3;r.push(Math.hypot(t[n]-t[e],t[n+1]-t[e+1],t[n+2]-t[e+2]))}let a=r.filter(e=>e>0).sort((e,t)=>e-t);return a.length?a[Math.floor(a.length/2)]*.35:Math.max(og(e.header.bbox)*.003,1e-6)}function cg(e,t){let n=t?10:2,r=t?20:8;return e.segments.reduce((e,t)=>e+(Math.max(1,t.n_points-1)*n+1)*(r+1),0)}function lg(e,t=!1){return e.n_segments<=3e3&&e.n_points<=5e5&&cg(e,t)<=6e6}function ug(){let{field:e,cellValues:t,categories:n}=sr();return(0,g.useMemo)(()=>{if(!e||!n)return null;let r=new Map,i=0;if(t)for(let e of t.values())typeof e==`string`?r.set(e,(r.get(e)??0)+1):i++;else for(let t of e.categories??[])r.set(t.value,t.count);let a=new Map;for(let t of e.categories??[])a.set(t.value,a.size);for(let e of r.keys())a.has(e)||a.set(e,a.size);let o=[...a.keys()].map((e,t)=>({value:e,count:r.get(e)??0,color:te(A(t,e)),off:n.get(e)===-1}));return{field:e,rows:o,missing:i}},[e,t,n])}function dg(){let e=ug(),t=W(e=>U(e).hiddenCategories),n=W(e=>e.toggleCategory),r=W(e=>e.setHiddenCategories);if(!e)return null;let{field:i,rows:a,missing:o}=e,s=a.map(e=>e.value);return(0,G.jsxs)(`section`,{className:`legend`,children:[(0,G.jsxs)(`h2`,{children:[(0,G.jsxs)(`span`,{children:[$n(i.name),` `,(0,G.jsx)(`span`,{className:`muted`,children:a.length})]}),(0,G.jsxs)(`span`,{className:`legend-actions`,children:[(0,G.jsx)(`button`,{onClick:()=>r([]),disabled:!t.length,children:`all`}),(0,G.jsx)(`button`,{onClick:()=>r(s),disabled:t.length===s.length,children:`none`})]})]}),(0,G.jsxs)(`ul`,{className:`legend-list categories`,children:[a.map(e=>(0,G.jsxs)(`li`,{className:e.off?`off`:``,onClick:()=>n(e.value),onDoubleClick:()=>r(s.filter(t=>t!==e.value)),title:`${e.value}: ${e.count.toLocaleString(`en-US`)} cells · click to grey out / restore · double-click to show only this one`,children:[(0,G.jsx)(`span`,{className:`swatch`,style:{background:e.color}}),(0,G.jsx)(`span`,{className:`name`,children:e.value}),(0,G.jsx)(`span`,{className:`muted count`,children:e.count.toLocaleString(`en-US`)})]},e.value)),o>0&&(0,G.jsxs)(`li`,{className:`missing`,title:`Cells without a value (drawn grey)`,children:[(0,G.jsx)(`span`,{className:`swatch`,style:{background:te(E)}}),(0,G.jsx)(`span`,{className:`name muted`,children:`missing`}),(0,G.jsx)(`span`,{className:`muted count`,children:o.toLocaleString(`en-US`)})]})]})]})}function fg({inline:e=!1}){let t=W(U),n=W(Gn),r=ug(),i=W(e=>e.toggleCategory);if(t.overviewColor!==`field`||!t.cellField)return null;if(r)return e?(0,G.jsxs)(`div`,{className:`colorbar${e?` inline`:``} cats`,title:`Legend with cell counts in the side panel`,children:[(0,G.jsx)(`span`,{className:`colorbar-title`,children:$n(t.cellField)}),r.rows.map(e=>(0,G.jsx)(`span`,{className:`cat-dot${e.off?` off`:``}`,style:{background:e.color},title:`${e.value}: ${e.count.toLocaleString(`en-US`)} cells · click to grey out / restore`,onClick:()=>i(e.value)},e.value))]}):null;let[a,o]=n?D(n.values()):[0,1],s=Array.from({length:9},(e,t)=>`${te(T(t/8))} ${t/8*100}%`).join(`, `);return e?(0,G.jsxs)(`div`,{className:`colorbar inline`,title:`99th-percentile cap · grey = missing`,children:[(0,G.jsx)(`span`,{className:`colorbar-title`,children:$n(t.cellField)}),(0,G.jsx)(`span`,{className:`colorbar-tick`,children:n?Xn(a):`…`}),(0,G.jsx)(`span`,{className:`colorbar-ramp`,style:{background:`linear-gradient(to right, ${s})`}}),(0,G.jsx)(`span`,{className:`colorbar-tick`,children:n?`≥${Xn(o)}`:``})]}):(0,G.jsxs)(`div`,{className:`colorbar side`,children:[(0,G.jsx)(`div`,{className:`colorbar-title`,children:$n(t.cellField)}),(0,G.jsx)(`div`,{className:`colorbar-ramp`,style:{background:`linear-gradient(to right, ${s})`}}),(0,G.jsxs)(`div`,{className:`colorbar-ticks`,children:[(0,G.jsx)(`span`,{children:n?Xn(a):`…`}),(0,G.jsx)(`span`,{children:n?`≥${Xn(o)}`:``})]}),(0,G.jsx)(`div`,{className:`muted small`,children:`99th pct cap · grey = missing`})]})}function pg(e){return e===`rna`?`Gene`:e===`cell`?`Property`:e.length<=3?e.toUpperCase():e[0].toUpperCase()+e.slice(1)}function mg({fields:e,value:t,placeholder:n,onPick:r}){let i=e.find(e=>e.name===t),a=e=>e.group===`cell`?$n(e.name):e.label,[o,s]=(0,g.useState)(i?a(i):``),[c,l]=(0,g.useState)(!1);(0,g.useEffect)(()=>s(i?a(i):``),[t]);let u=(0,g.useMemo)(()=>e[0]?.group===`cell`?e:[...e].sort((e,t)=>e.label.localeCompare(t.label)),[e]),d=o.trim().toLowerCase(),f=!c||i&&a(i).toLowerCase()===d?u:u.filter(e=>a(e).toLowerCase().includes(d)),p=e=>{r(e.name),s(a(e)),l(!1)};return(0,G.jsxs)(`div`,{className:`field-picker`,children:[(0,G.jsx)(`input`,{value:o,placeholder:n,onFocus:e=>{l(!0),e.target.select()},onBlur:()=>setTimeout(()=>l(!1),150),onChange:e=>{s(e.target.value),l(!0)},onKeyDown:e=>{e.key===`Enter`&&f.length&&p(f[0]),e.key===`Escape`&&e.target.blur()}}),c&&(0,G.jsxs)(`ul`,{className:`field-options`,children:[f.slice(0,200).map(e=>(0,G.jsx)(`li`,{className:e.name===t?`selected`:``,onMouseDown:()=>p(e),children:a(e)},e.name)),!f.length&&(0,G.jsx)(`li`,{className:`muted`,children:`no match`})]})]})}var hg=`\0category`;function gg(){let e=W(U),t=W(e=>e.setOverviewColor),n=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)?.cell_fields),r=W(e=>e.setCellField),i=W(e=>Nn(e.datasets.find(t=>t.id===e.activeDatasetId))),a=W(e=>e.layers.find(t=>t.datasetId===e.activeDatasetId&&t.parentId===null)),o=W(e=>e.setStyle),s=Qn(n??[]),c=e.overviewColor,l=e=>e.kind===`category`?hg:e.group,u=new Map;s.some(e=>e.kind===`category`)&&u.set(hg,[]);for(let e of s)u.set(l(e),[...u.get(l(e))??[],e]);let d=e=>{if(e!==hg)return pg(e);let t=u.get(e)??[],n=t.length===1?$n(t[0].name):`Type`;return n[0].toUpperCase()+n.slice(1)},f=c===`field`?s.find(t=>t.name===e.cellField):void 0,p=f?l(f):void 0,m=t=>{let n=u.get(t)??[];n.length&&r(n.some(t=>t.name===e.cellField)?e.cellField:n[0].name)},h=i?[[`rainbow`,`Chrom`],[`trace`,`Trace`],[`custom`,`Custom`]]:[];return(0,G.jsxs)(`section`,{className:`overview-colour`,children:[(0,G.jsx)(`h2`,{children:`Colour · all cells`}),(0,G.jsxs)(`div`,{className:`seg`,children:[(0,G.jsx)(`button`,{className:c===`cell`?`active`:``,onClick:()=>t(`cell`),children:`Cell`}),[...u.keys()].map(e=>(0,G.jsx)(`button`,{className:p===e?`active`:``,onClick:()=>m(e),title:e===hg?`Colour cells by category`:`Colour cells by a ${pg(e).toLowerCase()}`,children:d(e)},e)),h.map(([e,n])=>(0,G.jsx)(`button`,{className:c===e?`active`:``,onClick:()=>t(e),children:n},e))]}),c===`custom`&&a&&(0,G.jsx)(`input`,{type:`color`,value:a.style.color,onChange:e=>o(a.id,{color:e.target.value})}),p&&(u.get(p)?.length??0)>1&&(0,G.jsx)(mg,{fields:u.get(p)??[],value:e.cellField,placeholder:`search ${d(p).toLowerCase()}…`,onPick:r},p),(0,G.jsx)(fg,{}),(0,G.jsx)(dg,{})]})}function _g({layer:e,hasCells:t}){let n=W(e=>e.setStyle),r=W(U),i=W(e=>e.setMaxBond),a=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)?.xyz_unit??``),o=e.style,s=t=>n(e.id,t),c=e.geometry?.header,l=new Set(r.hiddenChroms),u=c?.segments.filter(e=>!l.has(e.chrom)&&(r.focusCell===null||e.cell_id===r.focusCell)),d=e.geometry?sg(e.geometry):null,f=u?u.reduce((e,t)=>e+t.n_points,0):0,p=o.mode===`tube`&&c&&u&&!lg({...c,n_segments:u.length,n_points:f,segments:u},o.highQuality)?u.length:0,m=[[`rainbow`,`Rainbow`],[`trace`,`Trace`],[`custom`,`Custom`]],h=t?r.focusCell?`Colour · cell ${r.focusCell} & pinned cells`:`Colour · focused / pinned cells`:`Colour`;return(0,G.jsxs)(G.Fragment,{children:[(0,G.jsx)(`h2`,{children:`Style`}),(0,G.jsx)(`div`,{className:`prop-title`,children:e.name}),(0,G.jsxs)(`div`,{className:`muted small`,children:[`filter: `,jt(e.filter)]}),(0,G.jsx)(`label`,{children:`Render as`}),(0,G.jsx)(`div`,{className:`seg`,children:[`line`,`tube`,`points`].map(e=>(0,G.jsx)(`button`,{className:o.mode===e?`active`:``,onClick:()=>s({mode:e}),children:e},e))}),p>0&&(0,G.jsx)(`div`,{className:`note small`,children:t&&r.focusCell===null?(0,G.jsxs)(G.Fragment,{children:[`All cells are drawn as `,(0,G.jsx)(`b`,{children:`lines`}),`: at this zoom a tube is thinner than a pixel, and `,p.toLocaleString(`en-US`),` traces exceed the tube budget. Select a cell to see tubes.`]}):(0,G.jsxs)(G.Fragment,{children:[`Drawn as `,(0,G.jsx)(`b`,{children:`lines`}),`: `,p.toLocaleString(`en-US`),` traces exceed the tube budget. Create a subset or select a cell to see tubes.`]})}),(0,G.jsx)(`label`,{children:h}),(0,G.jsx)(`div`,{className:`seg`,children:m.map(([e,t])=>(0,G.jsx)(`button`,{className:o.colorMode===e?`active`:``,onClick:()=>s({colorMode:e}),children:t},e))}),o.colorMode===`custom`&&(0,G.jsx)(`input`,{type:`color`,value:o.color,onChange:e=>s({color:e.target.value})}),(0,G.jsxs)(`label`,{children:[`Opacity `,(0,G.jsx)(`span`,{className:`val`,children:o.opacity.toFixed(2)})]}),(0,G.jsx)(`input`,{type:`range`,min:.05,max:1,step:.05,value:o.opacity,onChange:e=>s({opacity:+e.target.value})}),o.mode===`line`&&(0,G.jsxs)(G.Fragment,{children:[(0,G.jsxs)(`label`,{children:[`Line width `,(0,G.jsxs)(`span`,{className:`val`,children:[o.lineWidth,`px`]})]}),(0,G.jsx)(`input`,{type:`range`,min:1,max:10,step:.5,value:o.lineWidth,onChange:e=>s({lineWidth:+e.target.value})})]}),o.mode===`tube`&&(0,G.jsxs)(G.Fragment,{children:[(0,G.jsxs)(`label`,{children:[`Tube radius `,(0,G.jsx)(`span`,{className:`val`,children:o.tubeRadius===null?`auto (${d?.toPrecision(3)??`—`})`:o.tubeRadius.toPrecision(3)})]}),(0,G.jsxs)(`div`,{className:`row`,children:[(0,G.jsx)(`input`,{type:`number`,step:`any`,min:0,placeholder:`auto`,value:o.tubeRadius??``,onChange:e=>s({tubeRadius:e.target.value===``?null:Math.max(0,+e.target.value)})}),(0,G.jsx)(`button`,{onClick:()=>s({tubeRadius:null}),disabled:o.tubeRadius===null,children:`auto`})]}),(0,G.jsxs)(`label`,{className:`check`,children:[(0,G.jsx)(`input`,{type:`checkbox`,checked:o.highQuality,onChange:e=>s({highQuality:e.target.checked})}),` High quality`]})]}),o.mode===`points`&&(0,G.jsxs)(G.Fragment,{children:[(0,G.jsxs)(`label`,{children:[`Point size `,(0,G.jsxs)(`span`,{className:`val`,children:[o.pointSize,`px`]})]}),(0,G.jsx)(`input`,{type:`range`,min:1,max:20,step:1,value:o.pointSize,onChange:e=>s({pointSize:+e.target.value})})]}),e.geometry&&o.mode!==`points`&&(0,G.jsx)(vg,{setting:r.maxBond,split:rg(e.geometry,r.maxBond),unit:a,onChange:i}),c&&(0,G.jsxs)(`dl`,{className:`stats`,children:[(0,G.jsxs)(`dt`,{children:[r.focusCell?`cell ${r.focusCell}`:`shown`,` points`]}),(0,G.jsx)(`dd`,{children:u.reduce((e,t)=>e+t.n_points,0).toLocaleString(`en-US`)}),(0,G.jsx)(`dt`,{children:`traces`}),(0,G.jsx)(`dd`,{children:new Set(u.map(e=>e.trace_id)).size.toLocaleString(`en-US`)}),(0,G.jsx)(`dt`,{children:`chroms`}),(0,G.jsx)(`dd`,{children:new Set(u.map(e=>e.chrom)).size}),(0,G.jsx)(`dt`,{className:`muted`,children:`layer points`}),(0,G.jsx)(`dd`,{className:`muted`,children:c.n_points.toLocaleString(`en-US`)})]}),c?.truncated&&(0,G.jsxs)(`div`,{className:`warn`,children:[`Truncated: showing `,c.n_points.toLocaleString(`en-US`),` of `,c.total_points.toLocaleString(`en-US`),` points. Create a subset to see everything.`]}),e.error&&(0,G.jsx)(`div`,{className:`error`,children:e.error})]})}function vg({setting:e,split:t,unit:n,onChange:r}){let i=e===null?`off`:`${e===`auto`?`auto (10× median) `:``}${t.threshold?.toPrecision(3)??`—`} ${n}`;return(0,G.jsxs)(G.Fragment,{children:[(0,G.jsxs)(`label`,{title:`Consecutive spots farther apart than this are not connected (unassigned spots, duplicated loci)`,children:[`Max bond `,(0,G.jsx)(`span`,{className:`val`,children:i})]}),(0,G.jsxs)(`div`,{className:`row`,children:[(0,G.jsx)(`input`,{type:`number`,step:`any`,min:0,placeholder:e===null?`off`:`auto`,value:typeof e==`number`?e:``,onChange:e=>r(e.target.value===``?`auto`:Math.max(0,+e.target.value))}),(0,G.jsx)(`button`,{onClick:()=>r(`auto`),disabled:e===`auto`,children:`auto`}),(0,G.jsx)(`button`,{onClick:()=>r(null),disabled:e===null,children:`off`})]}),e!==null&&(0,G.jsxs)(`div`,{className:`muted small`,children:[t.broken.toLocaleString(`en-US`),` long bonds cut`]})]})}var yg={left:62,top:14,right:16,bottom:44},bg={rg:`Rg per trace`,scaling:`Distance vs genomic distance`,hist:`Cell field histogram`,scatter:`Field scatter`};function xg(e,t){return[...e?[`rg`,`scaling`]:[],...t?[`hist`,`scatter`]:[]]}function Sg(e,t){return e.statsKind&&t.includes(e.statsKind)?e.statsKind:t[0]??null}function Cg({fields:e,value:t,onChange:n,title:r}){let i=new Map;for(let t of e)i.set(t.group,[...i.get(t.group)??[],t]);return(0,G.jsx)(`select`,{value:t,onChange:e=>n(e.target.value),title:r,children:[...i].map(([e,t])=>(0,G.jsx)(`optgroup`,{label:e===`rna`?`Gene`:e===`cell`?`Property`:e,children:[...t].sort((t,n)=>e===`cell`?0:t.label.localeCompare(n.label)).map(t=>(0,G.jsx)(`option`,{value:t.name,children:e===`cell`?$n(t.name):t.label},t.name))},e))})}function wg(e){let t=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)),n=W(e=>U(e).cellField),r=t?.has_coords!==!1&&(t?.n_spots??0)>0,i=(0,g.useMemo)(()=>Qn(t?.cell_fields??[]).filter(e=>e.kind!==`category`),[t]),a=xg(r,i.length>0),o=Sg(e,a),s=e.fieldX&&i.some(t=>t.name===e.fieldX)?e.fieldX:n&&i.some(e=>e.name===n)?n:i[0]?.name??null;return{ds:t,fields:i,kinds:a,kind:o,fx:s,fy:e.fieldY&&i.some(t=>t.name===e.fieldY)?e.fieldY:i.find(e=>e.name!==s)?.name??s}}function Tg({pane:e}){let t=W(e=>e.setWorkspace),{fields:n,kinds:r,kind:i,fx:a,fy:o}=wg(e),s=n=>t(t=>Sn(t,e.id,n));return i?(0,G.jsxs)(G.Fragment,{children:[(0,G.jsx)(`select`,{value:i,onChange:e=>s({statsKind:e.target.value}),title:`Chart`,children:r.map(e=>(0,G.jsx)(`option`,{value:e,children:bg[e]},e))}),(i===`rg`||i===`scaling`)&&(0,G.jsxs)(`select`,{value:e.chromScope??`all`,onChange:e=>s({chromScope:e.target.value}),title:`Chromosomes`,children:[(0,G.jsx)(`option`,{value:`all`,children:`all chromosomes`}),(0,G.jsx)(`option`,{value:`locus`,children:`locus chromosome`})]}),(i===`hist`||i===`scatter`)&&a&&(0,G.jsx)(Cg,{fields:n,value:a,onChange:e=>s({fieldX:e}),title:`x field`}),i===`scatter`&&o&&(0,G.jsxs)(G.Fragment,{children:[(0,G.jsx)(`span`,{className:`muted small`,children:`vs`}),(0,G.jsx)(Cg,{fields:n,value:o,onChange:e=>s({fieldY:e}),title:`y field`})]}),(i===`rg`||i===`scaling`)&&(0,G.jsx)(Eg,{pane:e})]}):null}function Eg({pane:e}){let t=W(e=>e.setWorkspace),n=yr(),r=[...n.fields.flatMap(e=>e.refs),...n.saved],i=pr(r),a=new Set(e.compareGroups??[]);if(!r.length)return null;let o=n=>t(t=>Sn(t,e.id,{compareGroups:a.has(n)?[...a].filter(e=>e!==n):[...a,n]}));return(0,G.jsxs)(`div`,{className:`compare-groups`,children:[(0,G.jsxs)(`div`,{className:`muted small`,children:[`compare groups`,a.size>0&&(0,G.jsx)(`button`,{className:`link`,onClick:()=>t(t=>Sn(t,e.id,{compareGroups:[]})),children:`none`})]}),(0,G.jsx)(`ul`,{className:`legend-list`,children:r.map((e,t)=>{let n=i[t];return(0,G.jsxs)(`li`,{className:a.has(e)?``:`off`,onClick:()=>o(e),title:a.has(e)?`Remove from the chart`:`Overlay on the chart`,children:[(0,G.jsx)(`span`,{className:`swatch round`,style:{background:n?.color??`#888`}}),(0,G.jsx)(`span`,{children:n?.name??e}),(0,G.jsx)(`span`,{className:`muted small`,children:n?.cells?n.cells.length:``})]},e)})})]})}function Dg(e,t){let n=W(n=>e&&t?n.cellValues[In(e,t)]:void 0),r=W(e=>e.setCellValues);return(0,g.useEffect)(()=>{if(!e||!t||n)return;let i=!0;return xe(e,t).then(n=>i&&r(e,t,new Map(n.cell_ids.map((e,t)=>[e,n.values[t]])))).catch(()=>void 0),()=>{i=!1}},[e,t,n,r]),n??null}function Og({pane:e}){let{ds:t,kind:n,fx:r,fy:i}=wg(e),a=gr(e),o=a.kind===`cell`?a.cell:null,s=a.kind===`group`?a.group:null,c=(0,g.useMemo)(()=>(e.compareGroups??[]).filter(e=>e!==s),[e.compareGroups,s]),l=pr([s,...c]),u=l[0],d=(0,g.useMemo)(()=>l.slice(1),[l]),f=W(e=>e.focusCell),p=W(U),m=W(e=>e.activeDatasetId?e.cells[e.activeDatasetId]:void 0),h=sr(),_=W(e=>e.layers.find(t=>t.datasetId===e.activeDatasetId&&t.parentId===null)?.style.color??`#ffffff`),{locus:v}=ti(),y=(0,g.useRef)(null),b=(0,g.useRef)(null),x=br(y),S=(e.chromScope??`all`)===`locus`?v?.chrom??null:null,[C,w]=(0,g.useState)(null),[T,E]=(0,g.useState)(null),[D,O]=(0,g.useState)({}),[k,A]=(0,g.useState)({}),[j,M]=(0,g.useState)(null),[N,P]=(0,g.useState)(null),F=Dg(t?.id,n===`hist`||n===`scatter`?r:null),ee=Dg(t?.id,n===`scatter`?i:null);(0,g.useEffect)(()=>{if(!t||n!==`rg`&&n!==`scaling`)return;let e=!0;return M(null),n===`rg`?Ie(t.id,{chrom:S,group:s}).then(t=>e&&w(t)).catch(t=>e&&M(t.message)):Promise.all([Le(t.id,{chrom:S,group:s}),o?Le(t.id,{chrom:S,cellId:o}).catch(()=>null):Promise.resolve(null)]).then(([t,n])=>e&&E({pop:t,cell:n})).catch(t=>e&&M(t.message)),()=>{e=!1}},[t?.id,n,S,s,n===`scaling`?o:null]);let te=c.join(``);(0,g.useEffect)(()=>{if(!t||n!==`rg`&&n!==`scaling`)return;let e=!0;O({}),A({});for(let r of c)n===`rg`?Ie(t.id,{chrom:S,group:r}).then(t=>e&&O(e=>({...e,[r]:t}))).catch(t=>e&&M(t.message)):Le(t.id,{chrom:S,group:r}).then(t=>e&&A(e=>({...e,[r]:t}))).catch(t=>e&&M(t.message));return()=>{e=!1}},[t?.id,n,S,te]);let I=(0,g.useMemo)(()=>{if(n!==`scatter`||!F||!ee)return null;let e=[...F.keys()].filter(e=>ee.has(e)),t=e=>typeof e==`number`?e:null;return{ids:e,X:e.map(e=>t(F.get(e))),Y:e.map(e=>t(ee.get(e)))}},[n,F,ee]),L={x:yg.left,y:yg.top,w:Math.max(10,x.w-yg.left-yg.right),h:Math.max(10,x.h-yg.top-yg.bottom)},ne=(0,g.useMemo)(()=>{if(!I)return null;let[e,t]=Zr(I.X),[n,r]=Zr(I.Y),i=Yr(e,t,L.x,L.x+L.w),a=Yr(n,r,L.y+L.h,L.y),o=new Float32Array(2*I.ids.length);return I.ids.forEach((e,t)=>{let n=I.X[t],r=I.Y[t],s=typeof n==`number`&&typeof r==`number`&&Number.isFinite(n)&&Number.isFinite(r);o[2*t]=s?i(n):NaN,o[2*t+1]=s?a(r):NaN}),{px:o,x0:e,x1:t,y0:n,y1:r,sx:i,sy:a}},[I,L.x,L.y,L.w,L.h]);(0,g.useEffect)(()=>{let e=b.current;if(!e||!x.w||!x.h||!t)return;let a=xr(e,x.w,x.h);if(!a)return;let l=t.xyz_unit??``;if(n===`rg`&&C){let e=c.map((e,t)=>({info:d[t],data:D[e]})).filter(e=>!!e.data),t=s?pt({kind:`group`,group:s},u):`all cells`,n=[...C.rg,...e.flatMap(e=>e.data.rg)],r=Math.min(...n.filter(e=>typeof e==`number`)),i=Math.max(...n.filter(e=>typeof e==`number`)),f=Number.isFinite(r)&&Number.isFinite(i)&&i>r?[r,i]:void 0,p=Jr(C.rg,40,f),m=e.length>0,h=e=>{let t=e.counts.reduce((e,t)=>e+t,0)||1;return m?e.counts.map(e=>e/t):e.counts},g=h(p),_=e.map(e=>({...e,counts:h(Jr(e.data.rg,40,f??[p.edges[0],p.edges[p.edges.length-1]]))})),v=Math.max(m?1e-9:1,...g,..._.flatMap(e=>e.counts)),y=Yr(p.edges[0],p.edges[p.edges.length-1],L.x,L.x+L.w),b=Yr(0,v,L.y+L.h,L.y);a.fillStyle=s&&u?u.color:`rgba(92,157,237,0.75)`,a.globalAlpha=m?.35:s?.8:1,g.forEach((e,t)=>{let n=y(p.edges[t]);a.fillRect(n+.5,b(e),Math.max(1,y(p.edges[t+1])-n-1),L.y+L.h-b(e))}),a.globalAlpha=1;for(let e of _)a.strokeStyle=e.info?.color??`#ffffff`,a.lineWidth=2,a.beginPath(),e.counts.forEach((t,n)=>{let r=y(p.edges[n]),i=y(p.edges[n+1]);n===0&&a.moveTo(r,b(0)),a.lineTo(r,b(t)),a.lineTo(i,b(t)),n===e.counts.length-1&&a.lineTo(i,b(0))}),a.stroke();ui(a,L,{ticks:Kr(p.edges[0],p.edges[p.edges.length-1]),pos:y,fmt:$r,label:`radius of gyration${l?` (${l})`:``}`},{ticks:Kr(0,v,4),pos:b,fmt:$r,label:m?`fraction of traces`:`traces`});let x=e=>{let t=e.filter(e=>typeof e==`number`).sort((e,t)=>e-t);return t.length?t[Math.floor((t.length-1)/2)]:NaN};a.font=li.font,a.textAlign=`right`;let S=[{color:s&&u?u.color:li.accent,text:`${t}: median ${$r(x(C.rg))} · ${C.rg.length} traces${C.n_cells?` / ${C.n_cells} cells`:``}`},...e.map(e=>({color:e.info?.color??`#fff`,text:`${e.info?.name??e.data.group}: median ${$r(x(e.data.rg))} · ${e.data.rg.length} traces${e.data.n_cells?` / ${e.data.n_cells} cells`:``}`}))];S.forEach((e,t)=>{a.fillStyle=e.color,a.fillText(e.text,L.x+L.w,L.y+10+14*t)}),o&&(a.strokeStyle=`#ffffff`,a.lineWidth=2,C.cell_ids.forEach((e,t)=>{let n=C.rg[t];if(e!==o||typeof n!=`number`)return;let r=y(n);a.beginPath(),a.moveTo(r,L.y),a.lineTo(r,L.y+L.h),a.stroke()}),a.fillStyle=li.text,a.fillText(`white: traces of cell ${o}`,L.x+L.w,L.y+10+14*S.length))}else if(n===`scaling`&&T){let e=c.map((e,t)=>({info:d[t],data:k[e]})).filter(e=>!!e.data&&e.data.sep_bp.length>0),t=[T.pop,...T.cell?[T.cell]:[],...e.map(e=>e.data)],n=t.flatMap(e=>e.sep_bp).filter(e=>e>0),r=t.flatMap(e=>[...e.q25,...e.q75,...e.median]).filter(e=>typeof e==`number`&&e>0);if(!n.length||!r.length)return;let[i,f]=[Math.min(...n),Math.max(...n)],[p,m]=[Math.min(...r),Math.max(...r)],h=Xr(i,f>i?f:i*10,L.x,L.x+L.w),g=Xr(p,m>p?m:p*10,L.y+L.h,L.y),_=(e,t,n,r=`rgba(92,157,237,0.18)`)=>{let i=e.sep_bp.map((t,n)=>({x:t,m:e.median[n],a:e.q25[n],b:e.q75[n]})).filter(e=>e.x>0&&typeof e.m==`number`&&e.m>0);n&&(a.fillStyle=r,a.beginPath(),i.forEach((e,t)=>t?a.lineTo(h(e.x),g(e.b??e.m)):a.moveTo(h(e.x),g(e.b??e.m))),[...i].reverse().forEach(e=>a.lineTo(h(e.x),g(e.a&&e.a>0?e.a:e.m))),a.closePath(),a.fill()),a.strokeStyle=t,a.lineWidth=2,a.beginPath(),i.forEach((e,t)=>t?a.lineTo(h(e.x),g(e.m)):a.moveTo(h(e.x),g(e.m))),a.stroke()},v=s&&u?u.color:li.accent;_(T.pop,v,!0,s&&u?u.color.replace(`rgb(`,`rgba(`).replace(`)`,`, 0.18)`):void 0);for(let t of e)_(t.data,t.info?.color??`#ffffff`,!1);T.cell&&_(T.cell,`#ffffff`,!1);let y=qr(p,m);ui(a,L,{ticks:qr(i,f),pos:h,fmt:H,label:`genomic separation (bp, log)`},{ticks:y.length>=2?y:Kr(p,m,4),pos:g,fmt:$r,label:`median distance${l?` (${l})`:``}, log`}),a.font=li.font,a.textAlign=`left`,[{color:v,text:`${s?pt({kind:`group`,group:s},u):`population`} (median, IQR band)`},...e.map(e=>({color:e.info?.color??`#fff`,text:`${e.info?.name??e.data.group}${e.data.n_cells?` (${e.data.n_cells} cells)`:``}`})),...T.cell?[{color:`#ffffff`,text:`cell ${o}`}]:[]].forEach((e,t)=>{a.fillStyle=e.color,a.fillText(e.text,L.x+8,L.y+10+14*t)})}else if(n===`hist`&&F&&r){let e=Jr(F.values(),40),t=Math.max(1,...e.counts),n=Yr(e.edges[0],e.edges[e.edges.length-1],L.x,L.x+L.w),i=Yr(0,t,L.y+L.h,L.y);a.fillStyle=`rgba(92,157,237,0.75)`,e.counts.forEach((t,r)=>{let o=n(e.edges[r]);a.fillRect(o+.5,i(t),Math.max(1,n(e.edges[r+1])-o-1),L.y+L.h-i(t))}),ui(a,L,{ticks:Kr(e.edges[0],e.edges[e.edges.length-1]),pos:n,fmt:$r,label:$n(r)},{ticks:Kr(0,t,4),pos:i,fmt:$r,label:`cells`});let s=o?F.get(o):void 0;typeof s==`number`&&(a.strokeStyle=`#ffffff`,a.lineWidth=2,a.beginPath(),a.moveTo(n(s),L.y),a.lineTo(n(s),L.y+L.h),a.stroke(),a.fillStyle=li.text,a.font=li.font,a.textAlign=`right`,a.fillText(`cell ${o}: ${$r(s)}`,L.x+L.w,L.y+10))}else if(n===`scatter`&&I&&ne&&r&&i){let e={cellIndex:new Map((m??[]).map((e,t)=>[e.cell_id,t])),...h},t=I.ids.length,n=t>3e3?1.8:t>800?2.6:3.6;for(let r=0;r<t;r++){let t=ne.px[2*r];Number.isNaN(t)||(a.globalAlpha=o&&I.ids[r]!==o?.6:.95,a.fillStyle=fi(re(I.ids[r],p.overviewColor,_,e)),a.beginPath(),a.arc(t,ne.px[2*r+1],n,0,2*Math.PI),a.fill())}a.globalAlpha=1;let s=o?I.ids.indexOf(o):-1;s>=0&&!Number.isNaN(ne.px[2*s])&&(a.strokeStyle=`#ffffff`,a.lineWidth=2,a.beginPath(),a.arc(ne.px[2*s],ne.px[2*s+1],n*2+2,0,2*Math.PI),a.stroke()),ui(a,L,{ticks:Kr(ne.x0,ne.x1),pos:ne.sx,fmt:$r,label:$n(r)},{ticks:Kr(ne.y0,ne.y1,4),pos:ne.sy,fmt:$r,label:$n(i)})}},[n,C,T,F,r,i,I,ne,x.w,x.h,o,m,h,p.overviewColor,_,t,D,k,u,d]);let ie=e=>{if(!I||!ne)return-1;let t=e.currentTarget.getBoundingClientRect();return Nr(ne.px,e.clientX-t.left,e.clientY-t.top,8)},ae=e=>{let t=ie(e);if(t<0||!I)return P(null);let n=e.currentTarget.getBoundingClientRect();P({x:e.clientX-n.left,y:e.clientY-n.top,text:`cell ${I.ids[t]} · ${$r(I.X[t]??NaN)}, ${$r(I.Y[t]??NaN)}`})},oe=e=>{let t=ie(e);t>=0&&I&&f(I.ids[t])},se=null;return n?n===`scaling`&&T&&!T.pop.sep_bp.length&&(se=`No trace pairs to measure.`):se=`Nothing to chart: this dataset has neither 3-D traces nor numeric cell fields.`,(0,G.jsxs)(`div`,{ref:y,className:`genome-view`,children:[se&&(0,G.jsx)(`div`,{className:`muted pane-empty`,children:se}),j&&(0,G.jsx)(`div`,{className:`error pane-error`,children:j}),(0,G.jsx)(`canvas`,{ref:b,onMouseMove:ae,onMouseLeave:()=>P(null),onClick:oe,style:{cursor:N?`pointer`:`default`}}),(n===`rg`||n===`scaling`)&&(S||s)&&(0,G.jsx)(`div`,{className:`pane-badge small`,children:[S,s?pt(a,u):null].filter(Boolean).join(` · `)}),N&&(0,G.jsx)(`div`,{className:`embedding-tip`,style:{left:Math.min(N.x+12,x.w-200),top:N.y+12},children:N.text})]})}function kg(){let e=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)),t=W(e=>(e.activeDatasetId&&e.cells[e.activeDatasetId]||[]).length);return e?{hasCoords:Nn(e),nCells:t,nChroms:e.chroms.length,nPointSets:e.point_sets?.length??0}:null}function Ag(){let e=W(e=>e.workspace),t=W(e=>e.setWorkspace),n=kg(),r=W(e=>e.layers.find(t=>t.id===e.selectedLayerId));(0,g.useEffect)(()=>t(kr),[e.activePane,e.panes,t]);let i=e.panes.find(t=>t.id===e.activePane)??e.panes[0];if(!i)return(0,G.jsx)(`aside`,{className:`props panel inspector`});let a=new Set(Dr(i,n));return(0,G.jsxs)(`aside`,{className:`props panel inspector`,children:[(0,G.jsxs)(`div`,{className:`insp-title`,children:[(0,G.jsx)(`span`,{children:Or(e,i)}),(0,G.jsx)(`span`,{className:`muted small`,children:`inspector`})]}),a.has(`pin`)&&(0,G.jsxs)(`div`,{className:`insp-pin`,children:[(0,G.jsx)(`span`,{className:`insp-label`,children:`cells`}),(0,G.jsx)(ci,{value:i.scope,onChange:e=>e.kind!==`view`&&t(t=>hn(t,i.id,e)),title:`Which cells this view shows (genome rows can override it)`})]}),a.has(`noCoords`)&&(0,G.jsx)(`p`,{className:`muted small`,children:`This dataset has no 3-D coordinates — use a Genome, Matrix or Embedding view.`}),a.has(`layers`)&&(0,G.jsx)(Bi,{}),a.has(`subset`)&&(0,G.jsx)(Ki,{}),a.has(`style`)&&(r?(0,G.jsx)(_g,{layer:r,hasCells:(n?.nCells??0)>1}):(0,G.jsxs)(G.Fragment,{children:[(0,G.jsx)(`h2`,{children:`Style`}),(0,G.jsx)(`p`,{className:`muted`,children:`Select a layer.`})]})),a.has(`chroms`)&&(0,G.jsx)(Ar,{}),a.has(`points`)&&(0,G.jsx)(Zh,{}),a.has(`genomeRows`)&&(0,G.jsx)(Di,{pane:i}),a.has(`matrix`)&&(0,G.jsxs)(`section`,{className:`insp-controls`,children:[(0,G.jsx)(`h2`,{children:`Matrix`}),(0,G.jsx)(Ui,{pane:i})]}),a.has(`embedding`)&&(0,G.jsxs)(`section`,{className:`insp-controls`,children:[(0,G.jsx)(`h2`,{children:`Embedding`}),(0,G.jsx)(Ir,{pane:i})]}),a.has(`stats`)&&(0,G.jsxs)(`section`,{className:`insp-controls`,children:[(0,G.jsx)(`h2`,{children:`Chart`}),(0,G.jsx)(Tg,{pane:i})]})]},i.id)}function jg(){let e=W(e=>e.status),t=W(e=>e.error),n=W(e=>e.setError),r=W(e=>e.layers),i=W(e=>e.activeDatasetId),a=r.filter(e=>e.datasetId===i&&e.visible&&e.geometry),o=a.reduce((e,t)=>e+t.geometry.header.n_points,0),s=r.some(e=>e.loading),c=a.some(e=>e.geometry.header.truncated);return(0,G.jsxs)(`footer`,{className:`statusbar`,children:[(0,G.jsxs)(`span`,{children:[o.toLocaleString(`en-US`),` points in `,a.length,` visible layer`,a.length===1?``:`s`]}),s&&(0,G.jsx)(`span`,{children:`loading…`}),c&&(0,G.jsx)(`span`,{className:`warn`,children:`some layers are truncated`}),e&&(0,G.jsx)(`span`,{className:`warn`,children:e}),t&&(0,G.jsxs)(`span`,{className:`error`,onClick:()=>n(null),title:`Click to dismiss`,children:[t,` ✕`]})]})}function Mg(){let e=W(e=>e.datasets),t=W(e=>e.activeDatasetId),n=W(e=>e.setActiveDataset),r=W(e=>e.addDataset),i=W(e=>e.removeDataset),a=W(e=>e.setError),[o,s]=(0,g.useState)(!1),[c,l]=(0,g.useState)(``),[u,d]=(0,g.useState)(!1),f=e.find(e=>e.id===t),p=async()=>{if(c.trim()){d(!0);try{r(await ve(c.trim())),s(!1),l(``),a(null)}catch(e){a(`Open failed: ${e.message}`)}finally{d(!1)}}},m=async()=>{if(f)try{await ye(f.id),i(f.id)}catch(e){a(`Close failed: ${e.message}`)}};return(0,G.jsxs)(`header`,{className:`topbar`,children:[(0,G.jsxs)(`div`,{className:`brand`,children:[`U-Chrom `,(0,G.jsx)(`span`,{children:`Browser`})]}),(0,G.jsxs)(`select`,{value:t??``,onChange:e=>n(e.target.value||null),disabled:!e.length,children:[!e.length&&(0,G.jsx)(`option`,{value:``,children:`No dataset loaded`}),e.map(e=>(0,G.jsx)(`option`,{value:e.id,children:e.name},e.id))]}),o?(0,G.jsxs)(`form`,{className:`open-form`,onSubmit:e=>{e.preventDefault(),p()},children:[(0,G.jsx)(`input`,{autoFocus:!0,placeholder:`/path/to/data.h5cd or .csv (on the server)`,value:c,onChange:e=>l(e.target.value),onKeyDown:e=>e.key===`Escape`&&s(!1)}),(0,G.jsx)(`button`,{type:`submit`,disabled:u,children:u?`Loading…`:`Load`}),(0,G.jsx)(`button`,{type:`button`,onClick:()=>s(!1),children:`Cancel`})]}):(0,G.jsx)(`button`,{onClick:()=>s(!0),children:`Open…`}),f&&(0,G.jsx)(`button`,{onClick:()=>void m(),title:`Unload this dataset from the server`,children:`Close`}),f&&(0,G.jsxs)(`div`,{className:`summary`,title:f.path,children:[f.n_spots.toLocaleString(`en-US`),` spots · `,f.n_traces.toLocaleString(`en-US`),` traces ·`,` `,f.n_cells.toLocaleString(`en-US`),` cells · `,f.chroms.length,` chroms`,f.xyz_unit?` · ${f.xyz_unit}`:``]})]})}function Ng(){let e=W(U),t=W(e=>e.activeDatasetId&&e.cells[e.activeDatasetId]||null),n=W(e=>e.stepCell),r=W(e=>e.focusCell),i=W(e=>e.setContextOpacity),a=W(e=>e.openCellView),o=W(e=>e.focusGroup),s=W(e=>e.setWorkspace),c=W(e=>Nn(e.datasets.find(t=>t.id===e.activeDatasetId))),l=mr(e.focusGroup);if(e.focusGroup&&!e.focusCell)return(0,G.jsxs)(`div`,{className:`focus-bar`,children:[(0,G.jsxs)(`div`,{className:`focus-title`,children:[`group `,(0,G.jsx)(`span`,{className:`swatch round`,style:{display:`inline-block`,width:9,height:9,background:l?.color??`#888`}}),` `,(0,G.jsx)(`b`,{children:l?.name??e.focusGroup}),(0,G.jsxs)(`span`,{className:`muted`,children:[` · `,l?.cells?`${l.cells.length} cells`:`…`]})]}),(0,G.jsxs)(`label`,{className:`focus-ctx`,title:`Opacity of the other cells`,children:[`others`,(0,G.jsx)(`input`,{type:`range`,min:0,max:.6,step:.01,value:e.contextOpacity,onChange:e=>i(+e.target.value)})]}),(0,G.jsx)(`button`,{onClick:()=>s(t=>pn(t,c?`genome`:`matrix`,e.focusGroup)),title:`Open a new view aggregating over this group`,children:`↗ New view`}),(0,G.jsx)(`button`,{onClick:()=>o(null),title:`Back to all cells (Esc)`,children:`All cells`})]});if(!e.focusCell||!t?.length)return null;let u=t.findIndex(t=>t.cell_id===e.focusCell),d=t[u];return(0,G.jsxs)(`div`,{className:`focus-bar`,children:[(0,G.jsx)(`button`,{onClick:()=>n(-1),title:`Previous cell (←)`,children:`◀`}),(0,G.jsxs)(`div`,{className:`focus-title`,children:[`cell `,(0,G.jsx)(`b`,{children:e.focusCell}),(0,G.jsxs)(`span`,{className:`muted`,children:[` `,u+1,`/`,t.length,d&&` · ${d.n_traces} traces · ${d.n_chroms} chroms`]})]}),(0,G.jsx)(`button`,{onClick:()=>n(1),title:`Next cell (→)`,children:`▶`}),(0,G.jsxs)(`label`,{className:`focus-ctx`,title:`Opacity of the other cells`,children:[`others`,(0,G.jsx)(`input`,{type:`range`,min:0,max:.6,step:.01,value:e.contextOpacity,onChange:e=>i(+e.target.value)})]}),(0,G.jsx)(`button`,{onClick:()=>a(e.focusCell),title:`Open this cell in a new view pinned to it`,children:`↗ New view`}),(0,G.jsx)(`button`,{onClick:()=>r(null),title:`Back to all cells (Esc)`,children:`All cells`})]})}function Pg(){let{locus:e,chroms:t,ext:n,setLocus:r}=ti(),[i,a]=(0,g.useState)(``),[o,s]=(0,g.useState)(null);if((0,g.useEffect)(()=>{e&&a(Ur(e)),s(null)},[e?.chrom,e?.start,e?.end]),!e||!t.length)return null;let c=()=>{try{r(Hr(i,t,e)),s(null)}catch(e){s(e.message)}};return(0,G.jsxs)(`div`,{className:`locus-bar`,title:o??`Genomic window shared by the Tracks / Matrix / Stats views`,children:[(0,G.jsx)(`select`,{value:e.chrom,onChange:e=>{let n=t.find(t=>t.name===e.target.value);n&&r({chrom:n.name,start:n.start,end:n.end})},children:t.map(e=>(0,G.jsx)(`option`,{children:e.name},e.name))}),(0,G.jsx)(`input`,{className:o?`bad`:``,value:i,onChange:e=>a(e.target.value),onKeyDown:e=>e.key===`Enter`&&c(),onBlur:()=>e&&a(Ur(e)),spellCheck:!1}),(0,G.jsx)(`button`,{onClick:()=>r(Wr(e,.5,n)),title:`Zoom in`,children:`+`}),(0,G.jsx)(`button`,{onClick:()=>r(Wr(e,2,n)),title:`Zoom out`,children:`−`}),(0,G.jsx)(`button`,{onClick:()=>n&&r({chrom:n.name,start:n.start,end:n.end}),title:`Whole chromosome`,children:`full`})]})}function Fg(e){return e.trim().replace(/[^A-Za-z0-9._+-]+/g,`-`).replace(/-{2,}/g,`-`).replace(/^[-.]+|-+$/g,``)||`x`}var Ig=e=>String(e).padStart(2,`0`);function Lg(e){return`${e.getFullYear()}${Ig(e.getMonth()+1)}${Ig(e.getDate())}-${Ig(e.getHours())}${Ig(e.getMinutes())}${Ig(e.getSeconds())}`}function Rg(e){let t=[`uchrom`,e.dataset,nn[e.type].toLowerCase()],n=e.locus?`${e.locus.chrom}-${H(e.locus.start)}-${H(e.locus.end)}`:null;return n&&t.push(n),(e.scope||!n)&&t.push(e.scope||`all`),t.push(Lg(e.date)),`${t.map(Fg).join(`_`)}.png`}function zg(e){if(e.kind===`all`)return null;if(e.kind===`cell`)return`cell-${e.cell}`;let t=W.getState(),n=t.datasets.find(e=>e.id===t.activeDatasetId);return ft(e.group,{fields:n?.cell_fields??[],saved:Un(t),selection:U(t).selection,values:e=>n?t.cellValues[In(n.id,e)]:void 0})?.name??e.group}function Bg(e,t=new Date){let n=W.getState(),r=n.datasets.find(e=>e.id===n.activeDatasetId),i=U(n),a=e.type===`genome`||e.type===`matrix`;return Rg({dataset:r?.name??`data`,type:e.type,scope:zg(at(e.scope,i)),locus:a?ei(i.locus,zr(r)):null,date:t})}function Vg(e){for(let t=e;t;t=t.parentElement){let e=getComputedStyle(t).backgroundColor;if(e&&e!==`transparent`&&!/rgba\(.*,\s*0\)$/.test(e))return e}return`#1b1d21`}var Hg=`.embedding-tip, .gv-cross, .gv-row-loading, .gv-resize, [data-capture="skip"], button, input, select, textarea, label`;function Ug(e){let t=getComputedStyle(e);if(t.display===`none`||t.visibility===`hidden`||+t.opacity==0)return!1;let n=e.getBoundingClientRect();return n.width>0&&n.height>0}function Wg(e){return new Promise((t,n)=>{let r=new Image;r.onload=()=>t(r),r.onerror=()=>n(Error(`cannot rasterise an SVG`)),r.src=e})}var Gg=new Map;function Kg(e,t){t?Gg.set(e,t):Gg.delete(e)}async function qg(e){let t=e.dataset.pane;t&&Gg.get(t)?.();let n=e.getBoundingClientRect(),r=window.devicePixelRatio||1,i=document.createElement(`canvas`);i.width=Math.max(1,Math.round(n.width*r)),i.height=Math.max(1,Math.round(n.height*r));let a=i.getContext(`2d`);if(!a)throw Error(`no 2-D canvas context`);a.scale(r,r),a.fillStyle=Vg(e.querySelector(`canvas`)?.parentElement??e),a.fillRect(0,0,n.width,n.height);let o=e=>({x:e.left-n.left,y:e.top-n.top,w:e.width,h:e.height}),s=e=>!!e&&e!==`transparent`&&!/rgba\(.*,\s*0\)$/.test(e);for(let t of e.querySelectorAll(`*`)){if(t.closest(Hg)||t instanceof SVGElement&&!(t instanceof SVGSVGElement)||!Ug(t))continue;let e=o(t.getBoundingClientRect());if(t instanceof HTMLCanvasElement){a.drawImage(t,e.x,e.y,e.w,e.h);continue}if(t instanceof SVGSVGElement){let n=new XMLSerializer().serializeToString(t),r=URL.createObjectURL(new Blob([n],{type:`image/svg+xml`}));try{a.drawImage(await Wg(r),e.x,e.y,e.w,e.h)}finally{URL.revokeObjectURL(r)}continue}if(t.closest(`svg`))continue;let n=getComputedStyle(t);if(s(n.backgroundColor)&&!t.querySelector(`canvas, svg`)){a.fillStyle=n.backgroundColor;let t=Math.min(parseFloat(n.borderTopLeftRadius)||0,e.w/2,e.h/2);a.beginPath(),a.roundRect(e.x,e.y,e.w,e.h,t),a.fill()}for(let e of t.childNodes){if(e.nodeType!==Node.TEXT_NODE||!e.textContent?.trim())continue;let t=document.createRange();t.selectNodeContents(e);let r=o(t.getBoundingClientRect());r.w&&(a.font=`${n.fontStyle} ${n.fontWeight} ${n.fontSize} ${n.fontFamily}`,a.fillStyle=n.color,a.textBaseline=`middle`,a.textAlign=`left`,a.fillText(e.textContent.replace(/\s+/g,` `).trim(),r.x,r.y+r.h/2))}}return i}function Jg(e){return new Promise((t,n)=>e.toBlob(e=>e?t(e):n(Error(`PNG encoding failed`)),`image/png`))}async function Yg(e,t){let n=await qg(e);return{blob:await Jg(n),filename:Bg(t),width:n.width,height:n.height}}async function Xg(e,t){let{blob:n,filename:r}=await Yg(e,t),i=URL.createObjectURL(n),a=document.createElement(`a`);return a.href=i,a.download=r,document.body.appendChild(a),a.click(),a.remove(),setTimeout(()=>URL.revokeObjectURL(i),1e4),r}async function Zg(e,t={}){let n=W.getState().workspace.panes.find(t=>t.id===e),r=document.querySelector(`.pane-body[data-pane="${e}"]`);if(!n||!r)throw Error(`no pane ${e}`);let{blob:i,filename:a,width:o,height:s}=await Yg(r,n);return{filename:a,bytes:i.size,width:o,height:s,...t.url?{url:URL.createObjectURL(i)}:{}}}typeof window<`u`&&(window.uchrom={...window.uchrom??{},capturePane:Zg,composePane:qg});var Qg={type:`change`},$g={type:`start`},e_={type:`end`},t_=1e-6,n_={NONE:-1,ROTATE:0,ZOOM:1,PAN:2,TOUCH_ROTATE:3,TOUCH_ZOOM_PAN:4},r_=new Y,i_=new Y,a_=new X,o_=new X,s_=new X,c_=new ds,l_=new X,u_=new X,d_=new X,f_=new X,p_=class extends Sf{constructor(e,t=null){super(e,t),this.screen={left:0,top:0,width:0,height:0},this.rotateSpeed=1,this.zoomSpeed=1.2,this.panSpeed=.3,this.rollSpeed=1,this.noRotate=!1,this.noZoom=!1,this.noPan=!1,this.multiTouchRoll=!1,this.staticMoving=!1,this.dynamicDampingFactor=.2,this.minDistance=0,this.maxDistance=1/0,this.minZoom=0,this.maxZoom=1/0,this.keys=[`KeyA`,`KeyS`,`KeyD`],this.mouseButtons={LEFT:Zi.ROTATE,MIDDLE:Zi.DOLLY,RIGHT:Zi.PAN},this.target=new X,this.state=n_.NONE,this.keyState=n_.NONE,this._lastPosition=new X,this._lastUp=new X,this._lastZoom=1,this._touchZoomDistanceStart=0,this._touchZoomDistanceEnd=0,this._touchRollAngle=0,this._touchRollPointerIds=``,this._lastAngle=0,this._lastRollAngle=0,this._eye=new X,this._movePrev=new Y,this._moveCurr=new Y,this._lastAxis=new X,this._zoomStart=new Y,this._zoomEnd=new Y,this._panStart=new Y,this._panEnd=new Y,this._pointers=[],this._pointerPositions={},this._onPointerMove=h_.bind(this),this._onPointerDown=m_.bind(this),this._onPointerUp=g_.bind(this),this._onPointerCancel=__.bind(this),this._onContextMenu=w_.bind(this),this._onMouseWheel=C_.bind(this),this._onKeyDown=y_.bind(this),this._onKeyUp=v_.bind(this),this._onTouchStart=T_.bind(this),this._onTouchMove=E_.bind(this),this._onTouchEnd=D_.bind(this),this._onMouseDown=b_.bind(this),this._onMouseMove=x_.bind(this),this._onMouseUp=S_.bind(this),this._target0=this.target.clone(),this._position0=this.object.position.clone(),this._up0=this.object.up.clone(),this._zoom0=this.object.zoom,t!==null&&(this.connect(t),this.handleResize()),this.update()}connect(e){super.connect(e),window.addEventListener(`keydown`,this._onKeyDown),window.addEventListener(`keyup`,this._onKeyUp),this.domElement.addEventListener(`pointerdown`,this._onPointerDown),this.domElement.addEventListener(`pointercancel`,this._onPointerCancel),this.domElement.addEventListener(`wheel`,this._onMouseWheel,{passive:!1}),this.domElement.addEventListener(`contextmenu`,this._onContextMenu),this.domElement.style.touchAction=`none`}disconnect(){window.removeEventListener(`keydown`,this._onKeyDown),window.removeEventListener(`keyup`,this._onKeyUp),this.domElement.removeEventListener(`pointerdown`,this._onPointerDown),this.domElement.ownerDocument.removeEventListener(`pointermove`,this._onPointerMove),this.domElement.ownerDocument.removeEventListener(`pointerup`,this._onPointerUp),this.domElement.removeEventListener(`pointercancel`,this._onPointerCancel),this.domElement.removeEventListener(`wheel`,this._onMouseWheel),this.domElement.removeEventListener(`contextmenu`,this._onContextMenu),this.domElement.style.touchAction=``}dispose(){this.disconnect()}handleResize(){let e=this.domElement.getBoundingClientRect(),t=this.domElement.ownerDocument.documentElement;this.screen.left=e.left+window.pageXOffset-t.clientLeft,this.screen.top=e.top+window.pageYOffset-t.clientTop,this.screen.width=e.width,this.screen.height=e.height}update(){if(this._eye.subVectors(this.object.position,this.target),this.noRotate||(this._rotateCamera(),this.multiTouchRoll===!0&&this._rollCamera()),this.noZoom||this._zoomCamera(),this.noPan||this._panCamera(),this.object.position.addVectors(this.target,this._eye),this.object.isPerspectiveCamera){this._checkDistances(),this.object.lookAt(this.target);let e=this._lastPosition.distanceToSquared(this.object.position)>t_,t=this._lastUp.distanceToSquared(this.object.up)>t_;(e||t)&&(this.dispatchEvent(Qg),this._lastPosition.copy(this.object.position),this._lastUp.copy(this.object.up))}else if(this.object.isOrthographicCamera){this.object.lookAt(this.target);let e=this._lastPosition.distanceToSquared(this.object.position)>t_,t=this._lastUp.distanceToSquared(this.object.up)>t_,n=this._lastZoom!==this.object.zoom;(e||t||n)&&(this.dispatchEvent(Qg),this._lastPosition.copy(this.object.position),this._lastUp.copy(this.object.up),this._lastZoom=this.object.zoom)}else console.warn(`THREE.TrackballControls: Unsupported camera type.`)}reset(){this.state=n_.NONE,this.keyState=n_.NONE,this.target.copy(this._target0),this.object.position.copy(this._position0),this.object.up.copy(this._up0),this.object.zoom=this._zoom0,this.object.updateProjectionMatrix(),this._eye.subVectors(this.object.position,this.target),this.object.lookAt(this.target),this.dispatchEvent(Qg),this._lastPosition.copy(this.object.position),this._lastUp.copy(this.object.up),this._lastZoom=this.object.zoom}_panCamera(){if(i_.copy(this._panEnd).sub(this._panStart),i_.lengthSq()){if(this.object.isOrthographicCamera){let e=(this.object.right-this.object.left)/this.object.zoom/this.domElement.clientWidth,t=(this.object.top-this.object.bottom)/this.object.zoom/this.domElement.clientWidth;i_.x*=e,i_.y*=t}i_.multiplyScalar(this._eye.length()*this.panSpeed),o_.copy(this._eye).cross(this.object.up).setLength(i_.x),o_.add(a_.copy(this.object.up).setLength(i_.y)),this.object.position.add(o_),this.target.add(o_),this.staticMoving?this._panStart.copy(this._panEnd):this._panStart.add(i_.subVectors(this._panEnd,this._panStart).multiplyScalar(this.dynamicDampingFactor))}}_rotateCamera(){f_.set(this._moveCurr.x-this._movePrev.x,this._moveCurr.y-this._movePrev.y,0);let e=f_.length();e?(this._eye.copy(this.object.position).sub(this.target),l_.copy(this._eye).normalize(),u_.copy(this.object.up).normalize(),d_.crossVectors(u_,l_).normalize(),u_.setLength(this._moveCurr.y-this._movePrev.y),d_.setLength(this._moveCurr.x-this._movePrev.x),f_.copy(u_.add(d_)),s_.crossVectors(f_,this._eye).normalize(),e*=this.rotateSpeed,c_.setFromAxisAngle(s_,e),this._eye.applyQuaternion(c_),this.object.up.applyQuaternion(c_),this._lastAxis.copy(s_),this._lastAngle=e):!this.staticMoving&&this._lastAngle&&(this._lastAngle*=Math.sqrt(1-this.dynamicDampingFactor),this._eye.copy(this.object.position).sub(this.target),c_.setFromAxisAngle(this._lastAxis,this._lastAngle),this._eye.applyQuaternion(c_),this.object.up.applyQuaternion(c_)),this._movePrev.copy(this._moveCurr)}_rollCamera(){let e=this._getTouchRollAngle();if(e)this._lastRollAngle=e*this.rollSpeed;else if(!this.staticMoving&&this._lastRollAngle)this._lastRollAngle*=Math.sqrt(1-this.dynamicDampingFactor);else return;l_.copy(this._eye).normalize(),c_.setFromAxisAngle(l_,this._lastRollAngle),this.object.up.applyQuaternion(c_)}_getTouchRollAngle(){let e=this._pointers[0],t=this._pointers[1];if(t===void 0||e.pointerType!==`touch`||t.pointerType!==`touch`)return this._touchRollPointerIds=``,0;let n=`${e.pointerId},${t.pointerId}`,r=this._pointerPositions[e.pointerId],i=this._pointerPositions[t.pointerId],a=Math.atan2(i.y-r.y,i.x-r.x);if(n!==this._touchRollPointerIds)return this._touchRollPointerIds=n,this._touchRollAngle=a,0;let o=a-this._touchRollAngle;return this._touchRollAngle=a,o>Math.PI?o-=2*Math.PI:o<-Math.PI&&(o+=2*Math.PI),o}_zoomCamera(){let e;this.state===n_.TOUCH_ZOOM_PAN?(e=this._touchZoomDistanceStart/this._touchZoomDistanceEnd,this._touchZoomDistanceStart=this._touchZoomDistanceEnd,this.object.isPerspectiveCamera?this._eye.multiplyScalar(e):this.object.isOrthographicCamera?(this.object.zoom=us.clamp(this.object.zoom/e,this.minZoom,this.maxZoom),this._lastZoom!==this.object.zoom&&this.object.updateProjectionMatrix()):console.warn(`THREE.TrackballControls: Unsupported camera type`)):(e=1+(this._zoomEnd.y-this._zoomStart.y)*this.zoomSpeed,e!==1&&e>0&&(this.object.isPerspectiveCamera?this._eye.multiplyScalar(e):this.object.isOrthographicCamera?(this.object.zoom=us.clamp(this.object.zoom/e,this.minZoom,this.maxZoom),this._lastZoom!==this.object.zoom&&this.object.updateProjectionMatrix()):console.warn(`THREE.TrackballControls: Unsupported camera type`)),this.staticMoving?this._zoomStart.copy(this._zoomEnd):this._zoomStart.y+=(this._zoomEnd.y-this._zoomStart.y)*this.dynamicDampingFactor)}_getMouseOnScreen(e,t){return r_.set((e-this.screen.left)/this.screen.width,(t-this.screen.top)/this.screen.height),r_}_getMouseOnCircle(e,t){return r_.set((e-this.screen.width*.5-this.screen.left)/(this.screen.width*.5),(this.screen.height+2*(this.screen.top-t))/this.screen.width),r_}_addPointer(e){this._pointers.push(e)}_removePointer(e){delete this._pointerPositions[e.pointerId];for(let t=0;t<this._pointers.length;t++)if(this._pointers[t].pointerId==e.pointerId){this._pointers.splice(t,1);return}}_trackPointer(e){let t=this._pointerPositions[e.pointerId];t===void 0&&(t=new Y,this._pointerPositions[e.pointerId]=t),t.set(e.pageX,e.pageY)}_getSecondPointerPosition(e){let t=e.pointerId===this._pointers[0].pointerId?this._pointers[1]:this._pointers[0];return this._pointerPositions[t.pointerId]}_checkDistances(){(!this.noZoom||!this.noPan)&&(this._eye.lengthSq()>this.maxDistance*this.maxDistance&&(this.object.position.addVectors(this.target,this._eye.setLength(this.maxDistance)),this._zoomStart.copy(this._zoomEnd)),this._eye.lengthSq()<this.minDistance*this.minDistance&&(this.object.position.addVectors(this.target,this._eye.setLength(this.minDistance)),this._zoomStart.copy(this._zoomEnd)))}};function m_(e){this.enabled!==!1&&(this._pointers.length===0&&(this.domElement.setPointerCapture(e.pointerId),this.domElement.ownerDocument.addEventListener(`pointermove`,this._onPointerMove),this.domElement.ownerDocument.addEventListener(`pointerup`,this._onPointerUp)),this._addPointer(e),e.pointerType===`touch`?this._onTouchStart(e):this._onMouseDown(e))}function h_(e){this.enabled!==!1&&(e.pointerType===`touch`?this._onTouchMove(e):this._onMouseMove(e))}function g_(e){this.enabled!==!1&&(e.pointerType===`touch`?this._onTouchEnd(e):this._onMouseUp(),this._removePointer(e),this._pointers.length===0&&(this.domElement.releasePointerCapture(e.pointerId),this.domElement.ownerDocument.removeEventListener(`pointermove`,this._onPointerMove),this.domElement.ownerDocument.removeEventListener(`pointerup`,this._onPointerUp)))}function __(e){this._removePointer(e)}function v_(){this.enabled!==!1&&(this.keyState=n_.NONE,window.addEventListener(`keydown`,this._onKeyDown))}function y_(e){this.enabled!==!1&&(window.removeEventListener(`keydown`,this._onKeyDown),this.keyState===n_.NONE&&(e.code===this.keys[n_.ROTATE]&&!this.noRotate?this.keyState=n_.ROTATE:e.code===this.keys[n_.ZOOM]&&!this.noZoom?this.keyState=n_.ZOOM:e.code===this.keys[n_.PAN]&&!this.noPan&&(this.keyState=n_.PAN)))}function b_(e){let t;switch(e.button){case 0:t=this.mouseButtons.LEFT;break;case 1:t=this.mouseButtons.MIDDLE;break;case 2:t=this.mouseButtons.RIGHT;break;default:t=-1}switch(t){case Zi.DOLLY:this.state=n_.ZOOM;break;case Zi.ROTATE:this.state=n_.ROTATE;break;case Zi.PAN:this.state=n_.PAN;break;default:this.state=n_.NONE}let n=this.keyState===n_.NONE?this.state:this.keyState;n===n_.ROTATE&&!this.noRotate?(this._moveCurr.copy(this._getMouseOnCircle(e.pageX,e.pageY)),this._movePrev.copy(this._moveCurr)):n===n_.ZOOM&&!this.noZoom?(this._zoomStart.copy(this._getMouseOnScreen(e.pageX,e.pageY)),this._zoomEnd.copy(this._zoomStart)):n===n_.PAN&&!this.noPan&&(this._panStart.copy(this._getMouseOnScreen(e.pageX,e.pageY)),this._panEnd.copy(this._panStart)),this.dispatchEvent($g)}function x_(e){let t=this.keyState===n_.NONE?this.state:this.keyState;t===n_.ROTATE&&!this.noRotate?this._moveCurr.copy(this._getMouseOnCircle(e.pageX,e.pageY)):t===n_.ZOOM&&!this.noZoom?this._zoomEnd.copy(this._getMouseOnScreen(e.pageX,e.pageY)):t===n_.PAN&&!this.noPan&&this._panEnd.copy(this._getMouseOnScreen(e.pageX,e.pageY))}function S_(){this.state=n_.NONE,this.dispatchEvent(e_)}function C_(e){if(this.enabled!==!1&&this.noZoom!==!0){switch(e.preventDefault(),e.deltaMode){case 2:this._zoomStart.y-=e.deltaY*.025;break;case 1:this._zoomStart.y-=e.deltaY*.01;break;default:this._zoomStart.y-=e.deltaY*25e-5}this.dispatchEvent($g),this.dispatchEvent(e_)}}function w_(e){this.enabled!==!1&&e.preventDefault()}function T_(e){switch(this._trackPointer(e),this._pointers.length){case 1:this.state=n_.TOUCH_ROTATE,this._moveCurr.copy(this._getMouseOnCircle(this._pointers[0].pageX,this._pointers[0].pageY)),this._movePrev.copy(this._moveCurr);break;default:this.state=n_.TOUCH_ZOOM_PAN;let e=this._pointers[0].pageX-this._pointers[1].pageX,t=this._pointers[0].pageY-this._pointers[1].pageY;this._touchZoomDistanceEnd=this._touchZoomDistanceStart=Math.sqrt(e*e+t*t);let n=(this._pointers[0].pageX+this._pointers[1].pageX)/2,r=(this._pointers[0].pageY+this._pointers[1].pageY)/2;this._panStart.copy(this._getMouseOnScreen(n,r)),this._panEnd.copy(this._panStart)}this.dispatchEvent($g)}function E_(e){switch(this._trackPointer(e),this._pointers.length){case 1:this._moveCurr.copy(this._getMouseOnCircle(e.pageX,e.pageY));break;default:let t=this._getSecondPointerPosition(e),n=e.pageX-t.x,r=e.pageY-t.y;this._touchZoomDistanceEnd=Math.sqrt(n*n+r*r);let i=(e.pageX+t.x)/2,a=(e.pageY+t.y)/2;this._panEnd.copy(this._getMouseOnScreen(i,a))}}function D_(e){switch(this._pointers.length){case 0:this.state=n_.NONE;break;case 1:this.state=n_.TOUCH_ROTATE,this._moveCurr.copy(this._getMouseOnCircle(e.pageX,e.pageY)),this._movePrev.copy(this._moveCurr);break;case 2:this.state=n_.TOUCH_ZOOM_PAN;for(let t=0;t<this._pointers.length;t++)if(this._pointers[t].pointerId!==e.pointerId){let e=this._pointerPositions[this._pointers[t].pointerId];this._moveCurr.copy(this._getMouseOnCircle(e.x,e.y)),this._movePrev.copy(this._moveCurr);break}}this.dispatchEvent(e_)}function O_(e,t=!1){let n=e[0].index!==null,r=new Set(Object.keys(e[0].attributes)),i=new Set(Object.keys(e[0].morphAttributes)),a={},o={},s=e[0].morphTargetsRelative,c=new ul,l=0;for(let u=0;u<e.length;++u){let d=e[u],f=0;if(n!==(d.index!==null))return console.error(`THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index `+u+`. All geometries must have compatible attributes; make sure index attribute exists among all geometries, or in none of them.`),null;for(let e in d.attributes){if(!r.has(e))return console.error(`THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index `+u+`. All geometries must have compatible attributes; make sure "`+e+`" attribute exists among all geometries, or in none of them.`),null;a[e]===void 0&&(a[e]=[]),a[e].push(d.attributes[e]),f++}if(f!==r.size)return console.error(`THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index `+u+`. Make sure all geometries have the same number of attributes.`),null;if(s!==d.morphTargetsRelative)return console.error(`THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index `+u+`. .morphTargetsRelative must be consistent throughout all geometries.`),null;for(let e in d.morphAttributes){if(!i.has(e))return console.error(`THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index `+u+`.  .morphAttributes must be consistent throughout all geometries.`),null;o[e]===void 0&&(o[e]=[]),o[e].push(d.morphAttributes[e])}if(t){let e;if(n)e=d.index.count;else if(d.attributes.position!==void 0)e=d.attributes.position.count;else return console.error(`THREE.BufferGeometryUtils: .mergeGeometries() failed with geometry at index `+u+`. The geometry must have either an index or a position attribute`),null;c.addGroup(l,e,u),l+=e}}if(n){let t=0,n=[];for(let r=0;r<e.length;++r){let i=e[r].index;for(let e=0;e<i.count;++e)n.push(i.getX(e)+t);t+=e[r].attributes.position.count}c.setIndex(n)}for(let e in a){let t=k_(a[e]);if(!t)return console.error(`THREE.BufferGeometryUtils: .mergeGeometries() failed while trying to merge the `+e+` attribute.`),null;c.setAttribute(e,t)}for(let e in o){let t=o[e][0].length;if(t!==0){c.morphAttributes=c.morphAttributes||{},c.morphAttributes[e]=[];for(let n=0;n<t;++n){let t=[];for(let r=0;r<o[e].length;++r)t.push(o[e][r][n]);let r=k_(t);if(!r)return console.error(`THREE.BufferGeometryUtils: .mergeGeometries() failed while trying to merge the `+e+` morphAttribute.`),null;c.morphAttributes[e].push(r)}}}return c}function k_(e){let t,n,r,i=-1,a=0;for(let o=0;o<e.length;++o){let s=e[o];if(t===void 0&&(t=s.array.constructor),t!==s.array.constructor)return console.error(`THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.array must be of consistent array types across matching attributes.`),null;if(n===void 0&&(n=s.itemSize),n!==s.itemSize)return console.error(`THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.itemSize must be consistent across matching attributes.`),null;if(r===void 0&&(r=s.normalized),r!==s.normalized)return console.error(`THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.normalized must be consistent across matching attributes.`),null;if(i===-1&&(i=s.gpuType),i!==s.gpuType)return console.error(`THREE.BufferGeometryUtils: .mergeAttributes() failed. BufferAttribute.gpuType must be consistent across matching attributes.`),null;a+=s.count*n}let o=new t(a),s=new Yc(o,n,r),c=0;for(let t=0;t<e.length;++t){let r=e[t];if(r.isInterleavedBufferAttribute){let e=c/n;for(let t=0,i=r.count;t<i;t++)for(let i=0;i<n;i++){let n=r.getComponent(t,i);s.setComponent(t+e,i,n)}}else o.set(r.array,c);c+=r.count*n}return i!==void 0&&(s.gpuType=i),s}var A_=new jc,j_=new X,M_=class extends Wd{constructor(){super(),this.isLineSegmentsGeometry=!0,this.type=`LineSegmentsGeometry`,this.setIndex([0,2,1,2,3,1,2,4,3,4,5,3,4,6,5,6,7,5]),this.setAttribute(`position`,new Qc([-1,2,0,1,2,0,-1,1,0,1,1,0,-1,0,0,1,0,0,-1,-1,0,1,-1,0],3)),this.setAttribute(`uv`,new Qc([-1,2,1,2,-1,1,1,1,-1,-1,1,-1,-1,-2,1,-2],2))}applyMatrix4(e){let t=this.attributes.instanceStart,n=this.attributes.instanceEnd;return t!==void 0&&(t.applyMatrix4(e),n.applyMatrix4(e),t.needsUpdate=!0),this.boundingBox!==null&&this.computeBoundingBox(),this.boundingSphere!==null&&this.computeBoundingSphere(),this}setPositions(e){let t;e instanceof Float32Array?t=e:Array.isArray(e)&&(t=new Float32Array(e));let n=new cf(t,6,1);return this.setAttribute(`instanceStart`,new pl(n,3,0)),this.setAttribute(`instanceEnd`,new pl(n,3,3)),this.instanceCount=this.attributes.instanceStart.count,this.computeBoundingBox(),this.computeBoundingSphere(),this}setColors(e){let t;e instanceof Float32Array?t=e:Array.isArray(e)&&(t=new Float32Array(e));let n=new cf(t,6,1);return this.setAttribute(`instanceColorStart`,new pl(n,3,0)),this.setAttribute(`instanceColorEnd`,new pl(n,3,3)),this}fromWireframeGeometry(e){return this.setPositions(e.attributes.position.array),this}fromEdgesGeometry(e){return this.setPositions(e.attributes.position.array),this}fromMesh(e){return this.fromWireframeGeometry(new qu(e.geometry)),this}fromLineSegments(e){let t=e.geometry;return this.setPositions(t.attributes.position.array),this}computeBoundingBox(){this.boundingBox===null&&(this.boundingBox=new jc);let e=this.attributes.instanceStart,t=this.attributes.instanceEnd;e!==void 0&&t!==void 0&&(this.boundingBox.setFromBufferAttribute(e),A_.setFromBufferAttribute(t),this.boundingBox.union(A_))}computeBoundingSphere(){this.boundingSphere===null&&(this.boundingSphere=new nl),this.boundingBox===null&&this.computeBoundingBox();let e=this.attributes.instanceStart,t=this.attributes.instanceEnd;if(e!==void 0&&t!==void 0){let n=this.boundingSphere.center;this.boundingBox.getCenter(n);let r=0;for(let i=0,a=e.count;i<a;i++)j_.fromBufferAttribute(e,i),r=Math.max(r,n.distanceToSquared(j_)),j_.fromBufferAttribute(t,i),r=Math.max(r,n.distanceToSquared(j_));this.boundingSphere.radius=Math.sqrt(r),isNaN(this.boundingSphere.radius)&&console.error(`THREE.LineSegmentsGeometry.computeBoundingSphere(): Computed radius is NaN. The instanced position data is likely to have NaN values.`,this)}}toJSON(){}};$.line={worldUnits:{value:1},linewidth:{value:1},resolution:{value:new Y},dashOffset:{value:0},dashScale:{value:1},dashSize:{value:1},gapSize:{value:1}},Of.line={uniforms:ed.merge([$.common,$.fog,$.line]),vertexShader:`
		#include <common>
		#include <color_pars_vertex>
		#include <fog_pars_vertex>
		#include <logdepthbuf_pars_vertex>
		#include <clipping_planes_pars_vertex>

		uniform float linewidth;
		uniform vec2 resolution;

		attribute vec3 instanceStart;
		attribute vec3 instanceEnd;

		attribute vec3 instanceColorStart;
		attribute vec3 instanceColorEnd;

		#ifdef WORLD_UNITS

			varying vec4 worldPos;
			varying vec3 worldStart;
			varying vec3 worldEnd;

			#ifdef USE_DASH

				varying vec2 vUv;

			#endif

		#else

			varying vec2 vUv;

		#endif

		#ifdef USE_DASH

			uniform float dashScale;
			attribute float instanceDistanceStart;
			attribute float instanceDistanceEnd;
			varying float vLineDistance;

		#endif

		float trimSegmentAlpha( const in vec4 start, const in vec4 end ) {

			// compute the interpolation factor needed to trim the segment so it terminates
			// between the camera plane and the near plane

			// conservative estimate of the near plane
			float a = projectionMatrix[ 2 ][ 2 ]; // 3nd entry in 3th column
			float b = projectionMatrix[ 3 ][ 2 ]; // 3nd entry in 4th column

			// we need different nearEstimate formula for reversed and default depth buffer
			// a is positive with a reversed depth buffer so it can be used for controlling the code flow
			float nearEstimate = ( a > 0.0 ) ? ( - b / ( a + 1.0 ) ) : ( - 0.5 * b / a );

			return ( nearEstimate - start.z ) / ( end.z - start.z );

		}

		void main() {

			#ifdef USE_COLOR

				vColor.xyz = ( position.y < 0.5 ) ? instanceColorStart : instanceColorEnd;

			#endif

			float aspect = resolution.x / resolution.y;

			// camera space
			vec4 start = modelViewMatrix * vec4( instanceStart, 1.0 );
			vec4 end = modelViewMatrix * vec4( instanceEnd, 1.0 );

			#ifdef USE_DASH

				float lineDistanceStart = dashScale * instanceDistanceStart;
				float lineDistanceEnd = dashScale * instanceDistanceEnd;

			#endif

			#ifdef WORLD_UNITS

				worldStart = start.xyz;
				worldEnd = end.xyz;

			#else

				vUv = uv;

			#endif

			// special case for perspective projection, and segments that terminate either in, or behind, the camera plane
			// clearly the gpu firmware has a way of addressing this issue when projecting into ndc space
			// but we need to perform ndc-space calculations in the shader, so we must address this issue directly
			// perhaps there is a more elegant solution -- WestLangley

			bool perspective = ( projectionMatrix[ 2 ][ 3 ] == - 1.0 ); // 4th entry in the 3rd column

			if ( perspective ) {

				if ( start.z < 0.0 && end.z >= 0.0 ) {

					float alpha = trimSegmentAlpha( start, end );
					end.xyz = mix( start.xyz, end.xyz, alpha );

					#ifdef USE_DASH

						lineDistanceEnd = mix( lineDistanceStart, lineDistanceEnd, alpha );

					#endif

				} else if ( end.z < 0.0 && start.z >= 0.0 ) {

					float alpha = trimSegmentAlpha( end, start );
					start.xyz = mix( end.xyz, start.xyz, alpha );

					#ifdef USE_DASH

						lineDistanceStart = mix( lineDistanceEnd, lineDistanceStart, alpha );

					#endif

				}

			}

			#ifdef USE_DASH

				vLineDistance = ( position.y < 0.5 ) ? lineDistanceStart : lineDistanceEnd;
				vUv = uv;

			#endif

			// clip space
			vec4 clipStart = projectionMatrix * start;
			vec4 clipEnd = projectionMatrix * end;

			// ndc space
			vec3 ndcStart = clipStart.xyz / clipStart.w;
			vec3 ndcEnd = clipEnd.xyz / clipEnd.w;

			// direction
			vec2 dir = ndcEnd.xy - ndcStart.xy;

			// account for clip-space aspect ratio
			dir.x *= aspect;
			dir = normalize( dir );

			#ifdef WORLD_UNITS

				vec3 worldDir = normalize( end.xyz - start.xyz );
				vec3 tmpFwd = normalize( mix( start.xyz, end.xyz, 0.5 ) );
				vec3 worldUp = normalize( cross( worldDir, tmpFwd ) );
				vec3 worldFwd = cross( worldDir, worldUp );
				worldPos = position.y < 0.5 ? start: end;

				// height offset
				float hw = linewidth * 0.5;
				worldPos.xyz += position.x < 0.0 ? hw * worldUp : - hw * worldUp;

				// don't extend the line if we're rendering dashes because we
				// won't be rendering the endcaps
				#ifndef USE_DASH

					// cap extension
					worldPos.xyz += position.y < 0.5 ? - hw * worldDir : hw * worldDir;

					// add width to the box
					worldPos.xyz += worldFwd * hw;

					// endcaps
					if ( position.y > 1.0 || position.y < 0.0 ) {

						worldPos.xyz -= worldFwd * 2.0 * hw;

					}

				#endif

				// project the worldpos
				vec4 clip = projectionMatrix * worldPos;

				// shift the depth of the projected points so the line
				// segments overlap neatly
				vec3 clipPose = ( position.y < 0.5 ) ? ndcStart : ndcEnd;
				clip.z = clipPose.z * clip.w;

			#else

				vec2 offset = vec2( dir.y, - dir.x );
				// undo aspect ratio adjustment
				dir.x /= aspect;
				offset.x /= aspect;

				// sign flip
				if ( position.x < 0.0 ) offset *= - 1.0;

				// endcaps
				if ( position.y < 0.0 ) {

					offset += - dir;

				} else if ( position.y > 1.0 ) {

					offset += dir;

				}

				// adjust for linewidth
				offset *= linewidth;

				// adjust for clip-space to screen-space conversion // maybe resolution should be based on viewport ...
				offset /= resolution.y;

				// select end
				vec4 clip = ( position.y < 0.5 ) ? clipStart : clipEnd;

				// back to clip space
				offset *= clip.w;

				clip.xy += offset;

			#endif

			gl_Position = clip;

			vec4 mvPosition = ( position.y < 0.5 ) ? start : end; // this is an approximation

			#include <logdepthbuf_vertex>
			#include <clipping_planes_vertex>
			#include <fog_vertex>

		}
		`,fragmentShader:`
		uniform vec3 diffuse;
		uniform float opacity;
		uniform float linewidth;

		#ifdef USE_DASH

			uniform float dashOffset;
			uniform float dashSize;
			uniform float gapSize;

		#endif

		varying float vLineDistance;

		#ifdef WORLD_UNITS

			varying vec4 worldPos;
			varying vec3 worldStart;
			varying vec3 worldEnd;

			#ifdef USE_DASH

				varying vec2 vUv;

			#endif

		#else

			varying vec2 vUv;

		#endif

		#include <common>
		#include <color_pars_fragment>
		#include <fog_pars_fragment>
		#include <logdepthbuf_pars_fragment>
		#include <clipping_planes_pars_fragment>

		vec2 closestLineToLine(vec3 p1, vec3 p2, vec3 p3, vec3 p4) {

			float mua;
			float mub;

			vec3 p13 = p1 - p3;
			vec3 p43 = p4 - p3;

			vec3 p21 = p2 - p1;

			float d1343 = dot( p13, p43 );
			float d4321 = dot( p43, p21 );
			float d1321 = dot( p13, p21 );
			float d4343 = dot( p43, p43 );
			float d2121 = dot( p21, p21 );

			float denom = d2121 * d4343 - d4321 * d4321;

			float numer = d1343 * d4321 - d1321 * d4343;

			mua = numer / denom;
			mua = clamp( mua, 0.0, 1.0 );
			mub = ( d1343 + d4321 * ( mua ) ) / d4343;
			mub = clamp( mub, 0.0, 1.0 );

			return vec2( mua, mub );

		}

		void main() {

			float alpha = opacity;
			vec4 diffuseColor = vec4( diffuse, alpha );

			#include <clipping_planes_fragment>

			#ifdef USE_DASH

				if ( vUv.y < - 1.0 || vUv.y > 1.0 ) discard; // discard endcaps

				if ( mod( vLineDistance + dashOffset, dashSize + gapSize ) > dashSize ) discard; // todo - FIX

			#endif

			#ifdef WORLD_UNITS

				// Find the closest points on the view ray and the line segment
				vec3 rayEnd = normalize( worldPos.xyz ) * 1e5;
				vec3 lineDir = worldEnd - worldStart;
				vec2 params = closestLineToLine( worldStart, worldEnd, vec3( 0.0, 0.0, 0.0 ), rayEnd );

				vec3 p1 = worldStart + lineDir * params.x;
				vec3 p2 = rayEnd * params.y;
				vec3 delta = p1 - p2;
				float len = length( delta );
				float norm = len / linewidth;

				#ifndef USE_DASH

					#ifdef USE_ALPHA_TO_COVERAGE

						float dnorm = fwidth( norm );
						alpha = 1.0 - smoothstep( 0.5 - dnorm, 0.5 + dnorm, norm );

					#else

						if ( norm > 0.5 ) {

							discard;

						}

					#endif

				#endif

			#else

				#ifdef USE_ALPHA_TO_COVERAGE

					// artifacts appear on some hardware if a derivative is taken within a conditional
					float a = vUv.x;
					float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
					float len2 = a * a + b * b;
					float dlen = fwidth( len2 );

					if ( abs( vUv.y ) > 1.0 ) {

						alpha = 1.0 - smoothstep( 1.0 - dlen, 1.0 + dlen, len2 );

					}

				#else

					if ( abs( vUv.y ) > 1.0 ) {

						float a = vUv.x;
						float b = ( vUv.y > 0.0 ) ? vUv.y - 1.0 : vUv.y + 1.0;
						float len2 = a * a + b * b;

						if ( len2 > 1.0 ) discard;

					}

				#endif

			#endif

			#include <logdepthbuf_fragment>
			#include <color_fragment>

			gl_FragColor = vec4( diffuseColor.rgb, alpha );

			#include <tonemapping_fragment>
			#include <colorspace_fragment>
			#include <fog_fragment>
			#include <premultiplied_alpha_fragment>

		}
		`};var N_=class extends rd{constructor(e){super({type:`LineMaterial`,uniforms:ed.clone(Of.line.uniforms),vertexShader:Of.line.vertexShader,fragmentShader:Of.line.fragmentShader,clipping:!0}),this.isLineMaterial=!0,this.setValues(e)}get color(){return this.uniforms.diffuse.value}set color(e){this.uniforms.diffuse.value=e}get worldUnits(){return`WORLD_UNITS`in this.defines}set worldUnits(e){e===!0!==this.worldUnits&&(this.needsUpdate=!0),e===!0?this.defines.WORLD_UNITS=``:delete this.defines.WORLD_UNITS}get linewidth(){return this.uniforms.linewidth.value}set linewidth(e){this.uniforms.linewidth&&(this.uniforms.linewidth.value=e)}get dashed(){return`USE_DASH`in this.defines}set dashed(e){e===!0!==this.dashed&&(this.needsUpdate=!0),e===!0?this.defines.USE_DASH=``:delete this.defines.USE_DASH}get dashScale(){return this.uniforms.dashScale.value}set dashScale(e){this.uniforms.dashScale.value=e}get dashSize(){return this.uniforms.dashSize.value}set dashSize(e){this.uniforms.dashSize.value=e}get dashOffset(){return this.uniforms.dashOffset.value}set dashOffset(e){this.uniforms.dashOffset.value=e}get gapSize(){return this.uniforms.gapSize.value}set gapSize(e){this.uniforms.gapSize.value=e}get opacity(){return this.uniforms.opacity.value}set opacity(e){this.uniforms&&(this.uniforms.opacity.value=e)}get resolution(){return this.uniforms.resolution.value}set resolution(e){this.uniforms.resolution.value.copy(e)}get alphaToCoverage(){return`USE_ALPHA_TO_COVERAGE`in this.defines}set alphaToCoverage(e){this.defines&&(e===!0!==this.alphaToCoverage&&(this.needsUpdate=!0),e===!0?this.defines.USE_ALPHA_TO_COVERAGE=``:delete this.defines.USE_ALPHA_TO_COVERAGE)}},P_=new ks,F_=new X,I_=new X,L_=new ks,R_=new ks,z_=new ks,B_=new X,V_=new Ps,H_=new bf,U_=new X,W_=new jc,G_=new nl,K_=new ks,q_,J_;function Y_(e,t,n){return K_.set(0,0,-t,1).applyMatrix4(e.projectionMatrix),K_.multiplyScalar(1/K_.w),K_.x=J_/n.width,K_.y=J_/n.height,K_.applyMatrix4(e.projectionMatrixInverse),K_.multiplyScalar(1/K_.w),Math.abs(Math.max(K_.x,K_.y))}function X_(e,t){let n=e.matrixWorld,r=e.geometry,i=r.attributes.instanceStart,a=r.attributes.instanceEnd,o=Math.min(r.instanceCount,i.count);for(let r=0,s=o;r<s;r++){H_.start.fromBufferAttribute(i,r),H_.end.fromBufferAttribute(a,r),H_.applyMatrix4(n);let o=new X,s=new X;q_.distanceSqToSegment(H_.start,H_.end,s,o),s.distanceTo(o)<J_*.5&&t.push({point:s,pointOnLine:o,distance:q_.origin.distanceTo(s),object:e,face:null,faceIndex:r,uv:null,uv1:null})}}function Z_(e,t,n){let r=t.projectionMatrix,i=e.material.resolution,a=e.matrixWorld,o=e.geometry,s=o.attributes.instanceStart,c=o.attributes.instanceEnd,l=Math.min(o.instanceCount,s.count),u=-t.near;q_.at(1,z_),z_.w=1,z_.applyMatrix4(t.matrixWorldInverse),z_.applyMatrix4(r),z_.multiplyScalar(1/z_.w),z_.x*=i.x/2,z_.y*=i.y/2,z_.z=0,B_.copy(z_),V_.multiplyMatrices(t.matrixWorldInverse,a);for(let t=0,o=l;t<o;t++){if(L_.fromBufferAttribute(s,t),R_.fromBufferAttribute(c,t),L_.w=1,R_.w=1,L_.applyMatrix4(V_),R_.applyMatrix4(V_),L_.z>u&&R_.z>u)continue;if(L_.z>u){let e=L_.z-R_.z,t=(L_.z-u)/e;L_.lerp(R_,t)}else if(R_.z>u){let e=R_.z-L_.z,t=(R_.z-u)/e;R_.lerp(L_,t)}L_.applyMatrix4(r),R_.applyMatrix4(r),L_.multiplyScalar(1/L_.w),R_.multiplyScalar(1/R_.w),L_.x*=i.x/2,L_.y*=i.y/2,R_.x*=i.x/2,R_.y*=i.y/2,H_.start.copy(L_),H_.start.z=0,H_.end.copy(R_),H_.end.z=0;let o=H_.closestPointToPointParameter(B_,!0);H_.at(o,U_);let l=us.lerp(L_.z,R_.z,o),d=l>=-1&&l<=1,f=B_.distanceTo(U_)<J_*.5;if(d&&f){H_.start.fromBufferAttribute(s,t),H_.end.fromBufferAttribute(c,t),H_.start.applyMatrix4(a),H_.end.applyMatrix4(a);let r=new X,i=new X;q_.distanceSqToSegment(H_.start,H_.end,i,r),n.push({point:i,pointOnLine:r,distance:q_.origin.distanceTo(i),object:e,face:null,faceIndex:t,uv:null,uv1:null})}}}var Q_=class extends Ll{constructor(e=new M_,t=new N_({color:Math.random()*16777215})){super(e,t),this.isLineSegments2=!0,this.type=`LineSegments2`}computeLineDistances(){let e=this.geometry,t=e.attributes.instanceStart,n=e.attributes.instanceEnd,r=new Float32Array(2*t.count);for(let e=0,i=0,a=t.count;e<a;e++,i+=2)F_.fromBufferAttribute(t,e),I_.fromBufferAttribute(n,e),r[i]=i===0?0:r[i-1],r[i+1]=r[i]+F_.distanceTo(I_);let i=new cf(r,2,1);return e.setAttribute(`instanceDistanceStart`,new pl(i,1,0)),e.setAttribute(`instanceDistanceEnd`,new pl(i,1,1)),this}raycast(e,t){let n=this.material.worldUnits,r=e.camera;if(r===null&&!n&&console.error(`LineSegments2: "Raycaster.camera" needs to be set in order to raycast against LineSegments2 while worldUnits is set to false.`),n===!1&&(this.material.resolution.x===0||this.material.resolution.y===0))return;let i=e.params.Line2===void 0?0:e.params.Line2.threshold||0;q_=e.ray;let a=this.matrixWorld,o=this.geometry,s=this.material;J_=s.linewidth+i,o.boundingSphere===null&&o.computeBoundingSphere(),G_.copy(o.boundingSphere).applyMatrix4(a);let c;if(c=n?J_*.5:Y_(r,Math.max(r.near,G_.distanceToPoint(q_.origin)),s.resolution),G_.radius+=c,q_.intersectsSphere(G_)===!1)return;o.boundingBox===null&&o.computeBoundingBox(),W_.copy(o.boundingBox).applyMatrix4(a);let l;l=n?J_*.5:Y_(r,Math.max(r.near,W_.distanceToPoint(q_.origin)),s.resolution),W_.expandByScalar(l),q_.intersectsBox(W_)!==!1&&(n?X_(this,t):Z_(this,r,t))}onBeforeRender(e){let t=this.material.uniforms;t&&t.resolution&&(e.getViewport(P_),this.material.uniforms.resolution.value.set(P_.z,P_.w))}};function $_(e,t){e.transparent=t<1,e.opacity=t,e.depthWrite=t>=1}function ev(e,t,n={}){let r=ee(ie(e,t.colorMode,t.color,n)),i=t.mode,a=null;return i===`tube`&&!lg(e.header,t.highQuality)&&(i=`line`,a=`${e.header.n_segments.toLocaleString(`en-US`)} polyline segments exceed the tube budget — drawing lines (select a cell to see tubes)`),i===`points`?tv(e,r,t,a):i===`tube`?ov(e,r,t,a):iv(e,r,t,a)}function tv(e,t,n,r){let i=new ul;i.setAttribute(`position`,new Yc(e.positions,3)),i.setAttribute(`color`,new Yc(t,3)),i.computeBoundingSphere();let a=new iu({size:n.pointSize,sizeAttenuation:!1,vertexColors:!0});return $_(a,n.opacity),{object:new lu(i,a),pick:{kind:`vertex`},warning:r,dispose:()=>{i.dispose(),a.dispose()},setResolution:()=>{}}}function nv(e,t,n){let{offsets:r,positions:i}=e,a=[];for(let e=0;e+1<r.length;e++)r[e+1]-r[e]===1&&a.push(r[e]);if(!a.length)return null;let o=new Float32Array(3*a.length),s=new Float32Array(3*a.length);a.forEach((e,n)=>{o.set(i.subarray(3*e,3*e+3),3*n),s.set(t.subarray(3*e,3*e+3),3*n)});let c=new ul;c.setAttribute(`position`,new Yc(o,3)),c.setAttribute(`color`,new Yc(s,3)),c.computeBoundingSphere();let l=new iu({size:4,sizeAttenuation:!1,vertexColors:!0});$_(l,n);let u=new lu(c,l);return u.userData.singletons=Uint32Array.from(a),u}function rv(e,t,n,r){let i=nv(t,n,r);if(!i)return e;e.object.add(i);let a=e.dispose;return{...e,dispose:()=>{a(),i.geometry.dispose(),i.material.dispose()}}}function iv(e,t,n,r){return rv(av(e,t,n,r),e,t,n.opacity)}function av(e,t,n,r){let i=ig(e.offsets);if(n.lineWidth<=1){let a=new ul;a.setAttribute(`position`,new Yc(e.positions,3)),a.setAttribute(`color`,new Yc(t,3)),a.setIndex(new Yc(i,1)),a.computeBoundingSphere();let o=new Gl({vertexColors:!0});return $_(o,n.opacity),{object:new ru(a,o),pick:{kind:`indexed`,index:i},warning:r,dispose:()=>{a.dispose(),o.dispose()},setResolution:()=>{}}}let a=i.length/2,o=new Float32Array(a*6),s=new Float32Array(a*6);for(let n=0;n<a;n++)for(let r=0;r<2;r++){let a=i[2*n+r];for(let i=0;i<3;i++)o[6*n+3*r+i]=e.positions[3*a+i],s[6*n+3*r+i]=t[3*a+i]}let c=new M_;c.setPositions(o),c.setColors(s);let l=new N_({linewidth:n.lineWidth,vertexColors:!0,worldUnits:!1});return $_(l,n.opacity),{object:new Q_(c,l),pick:{kind:`pair`,pairIndex:i},warning:r,dispose:()=>{c.dispose(),l.dispose()},setResolution:(e,t)=>l.resolution.set(e,t)}}function ov(e,t,n,r){let i=n.tubeRadius??sg(e),a=n.highQuality?10:2,o=n.highQuality?20:8,s=[],c=[],{offsets:l,positions:u}=e;for(let e=0;e+1<l.length;e++){let n=l[e],r=l[e+1],d=r-n;if(d<2){let e=new Gu(i*1.5,o,Math.max(4,o/2));e.translate(u[3*n],u[3*n+1],u[3*n+2]);let r=e.attributes.position.count,a=new Float32Array(3*r);for(let e=0;e<r;e++)a.set(t.subarray(3*n,3*n+3),3*e),c.push(n);e.setAttribute(`color`,new Yc(a,3)),s.push(e);continue}let f=[];for(let e=n;e<r;e++)f.push(new X(u[3*e],u[3*e+1],u[3*e+2]));let p=new Eu(f,!1,`centripetal`),m=(d-1)*a,h=new Ku(p,m,i,o,!1),g=h.attributes.position.count,_=new Float32Array(3*g);for(let e=0;e<=m;e++){let r=e/m*(d-1),i=Math.floor(r),a=Math.min(d-1,i+1),s=r-i,l=n+i,u=n+a;for(let n=0;n<=o;n++){let r=e*(o+1)+n;for(let e=0;e<3;e++)_[3*r+e]=t[3*l+e]*(1-s)+t[3*u+e]*s;c.push(s<.5?l:u)}}h.setAttribute(`color`,new Yc(_,3)),s.push(h)}for(let e of s)for(let t of Object.keys(e.attributes))[`position`,`normal`,`color`].includes(t)||e.deleteAttribute(t);let d=s.length?O_(s,!1):new ul;s.forEach(e=>e.dispose()),d.computeBoundingSphere();let f=new ad({vertexColors:!0,roughness:.55,metalness:.05});return $_(f,n.opacity),{object:new Ll(d,f),pick:{kind:`tube`,pointOfVertex:Uint32Array.from(c)},warning:r,dispose:()=>{d.dispose(),f.dispose()},setResolution:()=>{}}}function sv(e,t){let n=t.object.userData.singletons;if(n)return t.index===void 0||t.index===null?-1:n[t.index];if(e.kind===`vertex`)return t.index??-1;if(e.kind===`indexed`){let n=t.index;return n==null?-1:e.index[n]}if(e.kind===`pair`){let n=t.faceIndex;return n==null?-1:e.pairIndex[2*n]}let r=t.face?.a;return r===void 0?-1:e.pointOfVertex[r]}function cv({paneId:e}){let t=W(e=>e.pick),n=W(e=>e.layers.find(t=>!xt(e.pick)&&t.id===e.pick?.layerId)),r=W(e=>(e.activeDatasetId&&e.cells[e.activeDatasetId]||[]).length>1),i=W(e=>e.openCellView),a=W(e=>e.setPick),o=(0,g.useRef)(null),[s,c]=(0,g.useState)(null);if((0,g.useLayoutEffect)(()=>{let e=o.current,n=e?.parentElement;if(!e||!n||!t)return c(null);let{x:r,y:i}=t.screen,a=e.offsetWidth,s=e.offsetHeight,l=r+14+a>n.clientWidth?Math.max(0,r-14-a):r+14,u=i+14+s>n.clientHeight?Math.max(0,i-14-s):i+14;c({left:l,top:u})},[t]),!t||e&&t.paneId&&t.paneId!==e)return null;let l=xt(t)?t.cellId:t.segment.cell_id,u=r&&l!==null?(0,G.jsx)(`button`,{className:`pick-open`,onClick:()=>{i(l),a(null)},title:`Open this cell in a new view pinned to it`,children:`↗ Open cell in new view`}):null;if(xt(t))return(0,G.jsxs)(`div`,{ref:o,className:`pick-label`,style:s??{left:t.screen.x+14,top:t.screen.y+14},children:[(0,G.jsxs)(`div`,{className:`pick-title`,children:[t.set.toUpperCase(),` `,t.label]}),t.cellId!==null&&(0,G.jsxs)(`div`,{children:[`cell `,t.cellId]}),Object.entries(t.values).map(([e,t])=>(0,G.jsxs)(`div`,{children:[e,` `,t===null?`—`:Xn(t)]},e)),(0,G.jsxs)(`div`,{className:`muted`,children:[`xyz `,t.position.map(e=>e.toFixed(2)).join(`, `)]}),u]});let d=t.segment;return(0,G.jsxs)(`div`,{ref:o,className:`pick-label`,style:s??{left:t.screen.x+14,top:t.screen.y+14},children:[(0,G.jsxs)(`div`,{className:`pick-title`,children:[`trace `,d.trace_id]}),d.cell_id!==null&&(0,G.jsxs)(`div`,{children:[`cell `,d.cell_id]}),(0,G.jsxs)(`div`,{children:[`bin `,d.chrom,`:`,t.binStart.toLocaleString(`en-US`)]}),(0,G.jsxs)(`div`,{children:[`segment `,d.chrom,`:`,H(d.start),`-`,H(d.end),` · `,d.n_points,` spots`]}),n&&(0,G.jsxs)(`div`,{className:`muted`,children:[`layer `,n.name]}),u]})}var lv=450;function uv(e){let t=new jc,n=!1;for(let r of e){let e=r?.header.bbox;r&&r.header.n_points!==0&&e&&(t.expandByPoint(new X(...e.min)),t.expandByPoint(new X(...e.max)),n=!0)}return n?t:null}function dv(e,t){let n=t.getCenter(new X),r=Math.max(t.getSize(new X).length()/2,1e-6)/Math.sin(us.degToRad(e.camera.fov/2))*1.1,i=e.camera.position.clone().sub(e.controls.target);return i.lengthSq()<1e-12&&i.set(0,0,1),i.normalize(),{target:n,pos:n.clone().add(i.multiplyScalar(r)),dist:r}}function fv(e,t){e.camera.near=Math.max(t/1e3,1e-6),e.camera.far=t*100,e.camera.updateProjectionMatrix()}function pv(e,t){let n=dv(e,t);e.fly=null,fv(e,n.dist),e.camera.position.copy(n.pos),e.controls.target.copy(n.target),e.controls.update()}function mv(e,t){let n=dv(e,t);e.camera.far=Math.max(e.camera.far,n.dist*100),e.camera.near=Math.min(e.camera.near,Math.max(n.dist/1e3,1e-6)),e.camera.updateProjectionMatrix(),e.fly={from:{pos:e.camera.position.clone(),target:e.controls.target.clone()},to:{pos:n.pos,target:n.target},t0:performance.now()}}var hv=e=>[...e].sort().join(`\0`);function gv(e){let t=[];for(let n of e.entries.values())for(let e of n.parts)e.role===`main`&&t.push(e.geometry);return t}function _v(e){let t=[];for(let n of e.entries.values())for(let e of n.parts)t.push(e.geometry);return t}function vv({paneId:e=`P1`,resetKey:t=0,scope:n}){let r=(0,g.useRef)(null),i=(0,g.useRef)(e);i.current=e;let a=(0,g.useRef)(null),o=(0,g.useRef)(null),s=(0,g.useRef)(!1),c=W(e=>e.layers),l=W(e=>e.activeDatasetId),u=W(U),d=W(e=>e.resetViewToken),f=W(e=>e.flyToken),p=W(e=>e.cells),m=sr(),h=W(e=>e.activeDatasetId?e.pointSets[e.activeDatasetId]:void 0),_=W(e=>e.setPick),v=W(e=>e.setStatus),y=gr({scope:n}),b=n?.kind===`cell`?n.cell:null,x=n&&n.kind!==`focus`?JSON.stringify(n):null,S=vr(y),C=y.kind===`all`?null:y.kind===`cell`?y.cell:S,w=b?0:u.contextOpacity,T=(0,g.useRef)(null);T.current=y.kind===`cell`?y.cell:null;let E=W(e=>{let t=e.datasets.find(t=>t.id===e.activeDatasetId);return!!t&&(t.has_coords===!1||t.n_spots===0)});(0,g.useEffect)(()=>{let e=r.current,t=new Hh({antialias:!0,preserveDrawingBuffer:!0});t.setPixelRatio(window.devicePixelRatio),t.setClearColor(new mc(getComputedStyle(document.documentElement).getPropertyValue(`--viewport-bg`).trim()||`#1b1d21`)),e.appendChild(t.domElement);let n=new gc,s=new zd(45,1,.01,1e6);s.position.set(0,0,10),n.add(s),n.add(new Ud(16777215,.55));let c=new Hd(16777215,1.6);c.position.set(1,1.5,2),s.add(c);let l=new cc;n.add(l);let u=new Ll(new Gu(1,16,12),new Tl({color:16777215,transparent:!0,opacity:.85,depthTest:!1}));u.visible=!1,u.renderOrder=999,n.add(u);let d=new xf(new jc,new mc(getComputedStyle(document.documentElement).getPropertyValue(`--accent`).trim()||`#5c9ded`));d.visible=!1,n.add(d);let f=new p_(s,t.domElement);f.rotateSpeed=3,f.zoomSpeed=3,f.panSpeed=.8,f.staticMoving=!0;let p={renderer:t,scene:n,camera:s,controls:f,group:l,entries:new Map,highlight:u,hoverBox:d,hover:null,points:new Map,fly:null};o.current=p;let m=()=>{let n=e.clientWidth,r=e.clientHeight;if(n&&r){t.setSize(n,r),s.aspect=n/r,s.updateProjectionMatrix(),f.handleResize();for(let e of p.entries.values())for(let t of e.parts)t.built.setResolution(n,r)}},h=new ResizeObserver(m);h.observe(e),m();let g=0,_=()=>{if(p.fly){let e=Math.min(1,(performance.now()-p.fly.t0)/lv),t=e<.5?4*e*e*e:1-(-2*e+2)**3/2;s.position.lerpVectors(p.fly.from.pos,p.fly.to.pos,t),f.target.lerpVectors(p.fly.from.target,p.fly.to.target,t),e>=1&&(fv(p,p.fly.to.pos.distanceTo(p.fly.to.target)),p.fly=null)}f.update(),t.render(n,s),g=requestAnimationFrame(_)};_();let v=null,y=e=>{v={x:e.clientX,y:e.clientY},p.fly=null},b=e=>{if(!v||e.button!==0)return;let t=Math.hypot(e.clientX-v.x,e.clientY-v.y);v=null,!(t>5)&&(xv(p,e,i.current,T.current),w())},x=a.current,S=null,C=0,w=()=>{Tv(p,null),d.visible=!1,x.style.display=`none`,t.domElement.style.cursor=``},E=e=>{if(e.buttons)return w();S=e,C||=requestAnimationFrame(()=>{C=0,S&&wv(p,S,x,T.current)})};return t.domElement.addEventListener(`pointerdown`,y),t.domElement.addEventListener(`pointerup`,b),t.domElement.addEventListener(`pointermove`,E),t.domElement.addEventListener(`pointerleave`,w),Kg(i.current,()=>{f.update(),t.render(n,s)}),()=>{Kg(i.current,null),cancelAnimationFrame(g),h.disconnect(),t.domElement.removeEventListener(`pointerdown`,y),t.domElement.removeEventListener(`pointerup`,b),t.domElement.removeEventListener(`pointermove`,E),t.domElement.removeEventListener(`pointerleave`,w),cancelAnimationFrame(C);for(let e of p.entries.values())for(let t of e.parts)t.built.dispose();for(let e of p.points.values())for(let t of e.parts)t.built.dispose();f.dispose(),t.dispose(),e.removeChild(t.domElement),o.current=null}},[]),(0,g.useEffect)(()=>{s.current=!1},[x]),(0,g.useEffect)(()=>{let e=o.current;if(!e)return;let t=c.filter(e=>e.datasetId===l&&e.visible&&e.geometry),n=new Set(t.map(e=>e.id)),r=(t,n)=>{for(let t of n.parts)e.group.remove(t.built.object),t.built.dispose();e.entries.delete(t)};for(let[t,i]of e.entries)n.has(t)||r(t,i);let i=new Set(u.hiddenChroms),a=l&&p[l]||[],d=new Map(a.map((e,t)=>[e.cell_id,t])),f=[],h=e.renderer.domElement.clientWidth,g=e.renderer.domElement.clientHeight;for(let n of t){let t={geometry:n.geometry,style:n.style,focus:C,hidden:hv(u.hiddenChroms),ctx:w,overview:u.overviewColor,nCells:a.length,values:u.overviewColor===`field`?m:null,maxBond:u.maxBond},o=e.entries.get(n.id);if(o&&o.key.geometry===t.geometry&&o.key.style===t.style&&o.key.focus===t.focus&&o.key.hidden===t.hidden&&o.key.ctx===t.ctx&&o.key.overview===t.overview&&o.key.nCells===t.nCells&&o.key.values===t.values&&o.key.maxBond===t.maxBond){for(let e of o.parts)e.built.warning&&f.push(`${n.name}: ${e.built.warning}`);continue}o&&r(n.id,o);let s=rg(n.geometry,u.maxBond).geometry,{main:c,context:l}=Gh(s,i,C),p={chromColors:new Set(n.geometry.header.segments.map(e=>e.chrom)).size>1,cellIndex:d,cellValues:t.values?.cellValues,fieldRange:t.values?.fieldRange,categories:t.values?.categories},_=d.size>1?{...n.style,colorMode:u.overviewColor}:n.style,v=typeof C==`string`?n.style:_,y=[];if(c&&y.push({role:`main`,geometry:c,built:ev(c,v,p)}),l&&w>0){let e=C!==null&&typeof C!=`string`?{..._,mode:`line`,lineWidth:1,opacity:w,colorMode:`custom`,color:`#6b7078`}:{..._,mode:`line`,lineWidth:1,opacity:w};y.push({role:`context`,geometry:l,built:ev(l,e,p)})}for(let t of y)t.built.object.userData={layerId:n.id,role:t.role},t.built.setResolution(h,g),t.role===`context`&&(t.built.object.renderOrder=-1),e.group.add(t.built.object),t.role===`main`&&t.built.warning&&f.push(`${n.name}: ${t.built.warning}`);e.entries.set(n.id,{key:t,parts:y})}if(v(f.length?f.join(` · `):null),!s.current){let t=uv(x&&C!==null?gv(e):_v(e));t&&(pv(e,t),s.current=!0)}let y=W.getState().pick;y&&!xt(y)&&!n.has(y.layerId)&&_(null)},[c,l,u,p,m,_,v,C,w,x]),(0,g.useEffect)(()=>{let e=o.current;if(!e)return;let t=h??{},n=new Set(u.hiddenPointSets);for(let[r,i]of e.points)if(!t[r]||n.has(r)){for(let t of i.parts)e.group.remove(t.built.object),t.built.dispose();e.points.delete(r)}for(let r of Object.values(t)){if(n.has(r.name))continue;let t=u.hiddenLabels[r.name]??[],i=[typeof C==`string`||C===null?C:`set:${[...C].join(`,`)}`,w,u.pointSize,[...t].sort().join(`\0`)].join(`|`),a=e.points.get(r.name);if(a&&a.set===r&&a.key===i)continue;if(a)for(let t of a.parts)e.group.remove(t.built.object),t.built.dispose();let o=Kh(r,new Set(t),C),s=[],c=typeof C!=`string`;o.main.length&&s.push({role:`main`,built:Xh(r,o.main,c?Math.max(2,u.pointSize*.5):u.pointSize,c?.85:1)}),o.context.length&&w>0&&s.push({role:`context`,built:Xh(r,o.context,Math.max(2,u.pointSize*.6),w)});for(let t of s)t.built.object.userData={kind:`points`,set:r.name,role:t.role},e.group.add(t.built.object);e.points.set(r.name,{set:r,key:i,parts:s})}},[h,u,C,w]),(0,g.useEffect)(()=>{s.current=!1;let e=o.current;if(!e)return;let t=uv(_v(e));t&&(pv(e,t),s.current=!0)},[d,l,t]);let D=(0,g.useRef)(x);D.current=x;let O=(0,g.useRef)(!1);O.current=C!==null,(0,g.useEffect)(()=>{let e=o.current;if(!e||f===0||D.current)return;let t=uv(O.current?gv(e):_v(e));t&&mv(e,t)},[f]);let k=W(e=>e.pick);return(0,g.useEffect)(()=>{let t=o.current;if(!t||(t.highlight.visible=!1,!k||k.paneId&&k.paneId!==e))return;if(xt(k)){t.highlight.position.set(...k.position),t.highlight.scale.setScalar(Math.max(t.camera.position.distanceTo(t.controls.target)*.01,1e-6)),t.highlight.visible=!0;return}let n=t.entries.get(k.layerId)?.parts.find(e=>e.role===`main`);if(!n)return;let r=n.geometry.positions,i=k.pointIndex;t.highlight.position.set(r[3*i],r[3*i+1],r[3*i+2]),t.highlight.scale.setScalar(Math.max(og(n.geometry.header.bbox)*.006,1e-6)),t.highlight.visible=!0},[k,e]),(0,G.jsxs)(`div`,{className:`viewport`,ref:r,children:[E&&(0,G.jsx)(`div`,{className:`muted pane-empty`,children:`No 3-D coordinates in this dataset — use Matrix / Tracks / Embedding views`}),(0,G.jsx)(cv,{paneId:e}),(0,G.jsx)(`div`,{className:`hover-tip`,ref:a})]})}function yv(e,t,n){let r=e.renderer.domElement.getBoundingClientRect(),i=new Y((t-r.left)/r.width*2-1,-((n-r.top)/r.height)*2+1),a=new uf,o=e.camera.position.distanceTo(e.controls.target)*.006;a.params.Line={threshold:o},a.params.Points={threshold:o},a.setFromCamera(i,e.camera);let s=null,c=1/0;for(let t of a.intersectObjects(e.group.children,!0)){let n=(t.object.userData.singletons&&t.object.parent?t.object.parent:t.object).userData,r=(t.distanceToRay??a.ray.distanceToPoint(t.point))/Math.max(t.distance,1e-9)+ +(n.role===`context`),i=null;if(n.kind===`points`){let a=e.points.get(n.set),o=a?.parts.find(e=>e.role===n.role);if(!a||!o||t.index===void 0||t.index===null)continue;let s=o.built.indices[t.index];i={kind:`point`,set:a.set,role:n.role,index:s,cell:a.set.cellIds[s]},r-=1e-4}else{let r=e.entries.get(n.layerId)?.parts.find(e=>e.role===n.role);if(!r)continue;let a=sv(r.built.pick,t);if(a<0)continue;let o=ag(r.geometry.offsets,a);if(o<0)continue;let s=r.geometry.header.segments[o];i={kind:`trace`,layerId:n.layerId,role:n.role,part:r,pointIndex:a,segment:s,cell:s.cell_id}}r<c&&(c=r,s=i)}return s}var bv=e=>(e.activeDatasetId&&e.cells[e.activeDatasetId]||[]).length>1;function xv(e,t,n,r){let i=W.getState(),a=yv(e,t.clientX,t.clientY);if(!a){i.setPick(null);return}if(bv(i)&&a.cell!==null&&a.cell!==r){i.focusCell(a.cell);return}let o=e.renderer.domElement.getBoundingClientRect(),s={x:t.clientX-o.left,y:t.clientY-o.top};if(a.kind===`point`){let e=a.set,t={};for(let[n,r]of Object.entries(e.values))t[n]=r[a.index]??null;let r=e.positions;i.setPick({kind:`point`,set:e.name,index:a.index,label:e.labels[a.index],cellId:a.cell,position:[r[3*a.index],r[3*a.index+1],r[3*a.index+2]],values:t,screen:s,paneId:n});return}i.setPick({kind:`trace`,layerId:a.layerId,pointIndex:a.pointIndex,segment:a.segment,binStart:a.part.geometry.starts[a.pointIndex],screen:s,paneId:n})}var Sv=new WeakMap;function Cv(e){let t=Sv.get(e);if(t)return t;t=new Map;let n=new X;return e.header.segments.forEach((r,i)=>{if(r.cell_id===null)return;let a=t.get(r.cell_id);a||t.set(r.cell_id,a=new jc);for(let t=e.offsets[i];t<e.offsets[i+1];t++)a.expandByPoint(n.fromArray(e.positions,3*t))}),Sv.set(e,t),t}function wv(e,t,n,r){let i=W.getState(),a=U(i),o=yv(e,t.clientX,t.clientY),s=e.renderer.domElement.getBoundingClientRect(),c=e=>{n.textContent=e,n.style.left=`${t.clientX-s.left+14}px`,n.style.top=`${t.clientY-s.top+14}px`,n.style.display=`block`},l=()=>{Tv(e,null),e.hoverBox.visible=!1,n.style.display=`none`,e.renderer.domElement.style.cursor=``},u=o?.cell??null,d=bv(i)&&u!==null&&u!==r,f=o?.kind===`point`?`${o.set.labels[o.index]}${u===null?``:` · cell ${u}`}`:null;if(!o||!d){l(),f&&c(f);return}let p=i.layers.find(e=>e.datasetId===i.activeDatasetId&&e.visible&&e.geometry)?.geometry,m=o.kind===`trace`?i.layers.find(e=>e.id===o.layerId)?.geometry:p;m&&Tv(e,u,rg(m,a.maxBond).geometry,new Set(a.hiddenChroms));let h=m?Cv(m).get(u):void 0;h&&(e.hoverBox.box.copy(h),e.hoverBox.visible=!0);let g=(i.activeDatasetId?i.cells[i.activeDatasetId]:void 0)?.find(e=>e.cell_id===u);c(`${f?`${f} — `:`cell ${u}${g?` · ${g.n_traces} traces`:``} — `}click to focus`),e.renderer.domElement.style.cursor=`pointer`}function Tv(e,t,n,r){if(e.hover&&e.hover.cell===t&&e.hover.geometry===n||(e.hover&&=(e.scene.remove(e.hover.built.object),e.hover.built.dispose(),null),t===null||!n))return;let i=Uh(n,e=>e.cell_id===t&&!r?.has(e.chrom));if(!i.header.n_points)return;let a=ev(i,{...gt,mode:`line`,colorMode:`custom`,color:`#ffffff`,lineWidth:2.5,opacity:1}),o=e.renderer.domElement;a.setResolution(o.clientWidth,o.clientHeight),a.object.renderOrder=998,a.object.traverse(e=>{let t=e.material;t&&(t.depthTest=!1)}),e.scene.add(a.object),e.hover={cell:t,geometry:n,built:a}}var Ev=nn,Dv={"3d":`3D view`,embedding:`Embedding view`,genome:`Genome (Hi-C / distance / tracks)`,matrix:`Matrix (Hi-C / distance)`,stats:`Statistics`},Ov=new Set([`genome`,`matrix`,`stats`]),kv={tabs:[`Tabs`,`One view at a time, switch with tabs`],columns:[`Columns`,`Views side by side`],rows:[`Rows`,`Views stacked`],grid:[`Grid`,`Views in a 2-column grid`]};function Av(){let e=W(e=>e.workspace),t=W(e=>e.setWorkspace),n=W(e=>e.ensureDefaultWorkspace),r=W(e=>e.activeDatasetId),i=W(e=>e.datasets.find(t=>t.id===e.activeDatasetId)),a=(i?.embeddings?.length??0)>0,o=!!i&&i.has_coords!==!1&&i.n_spots>0,s=(i?.tracks?.length??0)>0,c=(i?.contact_maps?.length??0)>0,[l,u]=(0,g.useState)({}),[d,f]=(0,g.useState)(!1),p=(0,g.useRef)(null);(0,g.useEffect)(()=>{r&&n({hasEmbeddings:a,hasCoords:o,hasTracks:s,hasContactMaps:c})},[r,a,o,s,c,n]);let m=W(e=>e.activeDatasetId?e.cells[e.activeDatasetId]:void 0);(0,g.useEffect)(()=>{m&&t(e=>bn(e,new Set(m.map(e=>e.cell_id))))},[m,t]);let h=i?.cell_fields,_=W(e=>Un(e));(0,g.useEffect)(()=>{if(!i)return;let e=new Set(_.map(e=>e.id)),n=t=>{let n=Ke(t);return n?!!h?.some(e=>e.name===n.field):e.has(t)};t(e=>yn(e,n))},[i,h,_,t]),(0,g.useEffect)(()=>{let e=e=>{let t=W.getState();kn(e,{hasPick:!!t.pick,clearPick:()=>t.setPick(null),clearFocus:()=>t.focusCell(null),step:e=>t.stepCell(e)})&&e.key!==`Escape`&&e.preventDefault()};return window.addEventListener(`keydown`,e),()=>window.removeEventListener(`keydown`,e)},[]);let v=ln(e.sizes,e.panes.length),y=(e.layout===`columns`||e.layout===`rows`)&&!e.maximized,b=t=>e.maximized?t.id===e.maximized:e.layout!==`tabs`||t.id===e.activePane,x=n=>r=>{r.preventDefault();let i=p.current?.getBoundingClientRect();if(!i)return;let a=e.layout===`columns`,o=e=>{let r=a?(e.clientX-i.left)/i.width:(e.clientY-i.top)/i.height;t(e=>Tn(e,n,r))},s=()=>{window.removeEventListener(`pointermove`,o),window.removeEventListener(`pointerup`,s),document.body.classList.remove(`resizing`,`resizing-rows`)};document.body.classList.add(a?`resizing`:`resizing-rows`),window.addEventListener(`pointermove`,o),window.addEventListener(`pointerup`,s)},S=e=>{t(t=>dn(t,e)),f(!1)};return(0,G.jsxs)(`div`,{className:`workspace`,children:[(0,G.jsxs)(`div`,{className:`ws-bar`,children:[(0,G.jsx)(Ng,{}),e.panes.some(e=>Ov.has(e.type))&&(0,G.jsx)(Pg,{}),(0,G.jsx)(`span`,{className:`spacer`}),(0,G.jsxs)(`div`,{className:`ws-add`,children:[(0,G.jsx)(`button`,{onClick:()=>f(!d),title:`Add a view`,children:`+ View`}),d&&(0,G.jsx)(`ul`,{className:`ws-menu`,onMouseLeave:()=>f(!1),children:tn.map(e=>(0,G.jsx)(`li`,{onClick:()=>S(e),children:Dv[e]},e))})]}),(0,G.jsx)(`div`,{className:`seg ws-layouts`,role:`group`,"aria-label":`Layout`,children:en.map(n=>(0,G.jsx)(`button`,{className:e.layout===n?`active`:``,title:kv[n][1],onClick:()=>t(e=>wn(e,n)),children:kv[n][0]},n))})]}),e.layout===`tabs`&&!e.maximized&&(0,G.jsx)(`div`,{className:`ws-tabs`,children:e.panes.map((n,r)=>(0,G.jsxs)(`button`,{className:n.id===e.activePane?`active`:``,onClick:()=>t(e=>({...e,activePane:n.id})),children:[Ev[n.type],` `,e.panes.filter(e=>e.type===n.type).length>1?r+1:``]},n.id))}),(0,G.jsx)(`div`,{ref:p,className:`ws-panes layout-${e.layout}${e.maximized?` maximized`:``}`,style:e.layout===`grid`&&!e.maximized?{gridTemplateColumns:e.panes.length>1?`1fr 1fr`:`1fr`}:void 0,children:e.panes.map((t,n)=>(0,G.jsxs)(g.Fragment,{children:[(0,G.jsx)(jv,{pane:t,active:t.id===e.activePane&&e.panes.length>1,hidden:!b(t),style:y?{flex:`${v[n]} 1 0`}:void 0,canClose:e.panes.length>1,maximized:e.maximized===t.id,resetKey:l[t.id]??0,onReset:()=>u(e=>({...e,[t.id]:(e[t.id]??0)+1}))}),y&&n<e.panes.length-1&&(0,G.jsx)(`div`,{className:`ws-splitter ${e.layout}`,onPointerDown:x(n),title:`Drag to resize`})]},t.id))})]})}function jv({pane:e,active:t,hidden:n,style:r,canClose:i,maximized:a,resetKey:o,onReset:s}){let c=W(e=>e.setWorkspace),l=()=>c(t=>t.activePane===e.id?t:{...t,activePane:e.id}),u=ii(),d=mr(_n(e)),f=gn(e),p=(0,g.useRef)(null),[m,h]=(0,g.useState)(!1);return(0,G.jsxs)(`section`,{className:`pane${t?` active`:``}${n?` hidden`:``}${e.scope&&e.scope.kind!==`focus`?` pinned`:``}`,style:r,onPointerDownCapture:l,onFocusCapture:l,children:[(0,G.jsxs)(`header`,{className:`pane-head`,children:[(0,G.jsx)(`select`,{value:e.type,onChange:t=>c(n=>Cn(n,e.id,t.target.value)),title:`View type`,children:tn.map(e=>(0,G.jsx)(`option`,{value:e,children:Ev[e]},e))}),f&&(0,G.jsxs)(`button`,{className:`pin-badge`,onClick:()=>l(),title:`Pinned to this cell — change it in the inspector (right, “cells”)`,children:[`📌 `,ai(f,u)]}),e.scope?.kind===`all`&&(0,G.jsx)(`button`,{className:`pin-badge`,onClick:()=>l(),title:`Always all cells — change it in the inspector (right, “cells”)`,children:`All cells`}),e.scope?.kind===`group`&&(0,G.jsxs)(`button`,{className:`pin-badge group`,onClick:()=>l(),title:`This view aggregates over a group of cells — change it in the inspector (right)`,children:[(0,G.jsx)(`span`,{className:`swatch round`,style:{background:d?.color??`#888`}}),d?.name??e.scope.group,d?.cells&&(0,G.jsxs)(`span`,{className:`muted`,children:[` · `,d.cells.length]})]}),(0,G.jsx)(`span`,{className:`spacer`}),(0,G.jsx)(`button`,{className:`pane-shot`,onClick:()=>{p.current&&!m&&(h(!0),Xg(p.current,e).catch(e=>W.getState().setError(`Cannot save the image: ${e.message}`)).finally(()=>h(!1)))},disabled:m,title:`Save image (PNG)`,"aria-label":`Save image (PNG)`,children:(0,G.jsxs)(`svg`,{viewBox:`0 0 16 16`,width:`13`,height:`13`,"aria-hidden":!0,children:[(0,G.jsx)(`path`,{d:`M2 5h2.6l1.2-1.8h4.4L11.4 5H14v8H2z`,fill:`none`,stroke:`currentColor`,strokeWidth:`1.3`,strokeLinejoin:`round`}),(0,G.jsx)(`circle`,{cx:`8`,cy:`9`,r:`2.3`,fill:`none`,stroke:`currentColor`,strokeWidth:`1.3`})]})}),e.type===`3d`&&(0,G.jsx)(`button`,{onClick:s,title:`Reset view: fit everything drawn in this view`,children:`⟲`}),(0,G.jsx)(`button`,{onClick:()=>c(t=>({...t,maximized:t.maximized===e.id?null:e.id,activePane:e.id})),title:a?`Restore layout`:`Maximise this view`,children:a?`⤡`:`⤢`}),(0,G.jsx)(`button`,{onClick:()=>c(t=>xn(t,e.id)),disabled:!i,title:i?`Close this view`:`The last view cannot be closed`,children:`×`})]}),(0,G.jsxs)(`div`,{className:`pane-body`,ref:p,"data-pane":e.id,children:[e.type===`3d`&&(0,G.jsx)(vv,{paneId:e.id,resetKey:o,scope:e.scope}),e.type===`embedding`&&(0,G.jsx)(Lr,{pane:e}),e.type===`genome`&&(0,G.jsx)(ji,{pane:e}),e.type===`matrix`&&(0,G.jsx)(Wi,{pane:e}),e.type===`stats`&&(0,G.jsx)(Og,{pane:e})]})]})}function Mv(e){let t=e?.match(/assets\/(index-[^/?#]+\.js)/);return t?t[1]:null}function Nv(e=document){for(let t of Array.from(e.querySelectorAll(`script[src]`))){let e=Mv(t.getAttribute(`src`));if(e)return e}return null}function Pv(e,t){return!!e&&!!t&&e!==t}var Fv="The server was started before this page was rebuilt and may lack newer features — restart `python -m uchrom.browser --web …` and reload.";function Iv(){let e=W(e=>e.datasets);(0,g.useEffect)(()=>{let{cells:t,setCells:n,setError:r}=W.getState();for(let i of e)i.n_cells<2||t[i.id]||(n(i.id,[]),be(i.id,{limit:1e5}).then(e=>n(i.id,e.cells)).catch(e=>r(`Cannot list cells: ${e.message}`)))},[e])}function Lv(){let e=W(e=>e.layers);(0,g.useEffect)(()=>{let{setLoading:t,setGeometry:n,setLayerError:r}=W.getState();for(let i of e){let e=W.getState().layers.find(e=>e.id===i.id);!e||e.geometry||e.loading||e.error||(t(i.id),V(i.datasetId,i.filter).then(e=>n(i.id,e)).catch(e=>r(i.id,e.message)))}},[e])}function Rv(){let e=W(e=>e.setDatasets),t=W(e=>e.setError);return Lv(),Iv(),ur(),(0,g.useEffect)(()=>{_e().then(e).catch(e=>t(`Cannot reach the U-Chrom server: ${e.message}`)),ge().then(e=>{Pv(Nv(),e.bundle??null)&&t(Fv)}).catch(()=>{})},[e,t]),(0,G.jsxs)(`div`,{className:`app`,children:[(0,G.jsx)(Mg,{}),(0,G.jsxs)(`div`,{className:`main`,children:[(0,G.jsx)(zv,{}),(0,G.jsx)(Av,{}),(0,G.jsx)(Ag,{})]}),(0,G.jsx)(jg,{})]})}function zv(){let e=new Set(Er(kg()));return(0,G.jsxs)(`div`,{className:`left`,children:[e.has(`cells`)&&(0,G.jsx)(wr,{}),e.has(`groups`)&&(0,G.jsx)(Tr,{}),e.has(`cellInfo`)&&(0,G.jsx)(`div`,{className:`panel left-info`,children:(0,G.jsx)(ar,{})}),e.has(`colour`)&&(0,G.jsx)(`div`,{className:`panel left-colour`,children:(0,G.jsx)(gg,{})})]})}(0,_.createRoot)(document.getElementById(`root`)).render((0,G.jsx)(g.StrictMode,{children:(0,G.jsx)(Rv,{})}));