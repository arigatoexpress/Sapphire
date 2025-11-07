function zy(t,e){for(var n=0;n<e.length;n++){const r=e[n];if(typeof r!="string"&&!Array.isArray(r)){for(const i in r)if(i!=="default"&&!(i in t)){const o=Object.getOwnPropertyDescriptor(r,i);o&&Object.defineProperty(t,i,o.get?o:{enumerable:!0,get:()=>r[i]})}}}return Object.freeze(Object.defineProperty(t,Symbol.toStringTag,{value:"Module"}))}(function(){const e=document.createElement("link").relList;if(e&&e.supports&&e.supports("modulepreload"))return;for(const i of document.querySelectorAll('link[rel="modulepreload"]'))r(i);new MutationObserver(i=>{for(const o of i)if(o.type==="childList")for(const l of o.addedNodes)l.tagName==="LINK"&&l.rel==="modulepreload"&&r(l)}).observe(document,{childList:!0,subtree:!0});function n(i){const o={};return i.integrity&&(o.integrity=i.integrity),i.referrerPolicy&&(o.referrerPolicy=i.referrerPolicy),i.crossOrigin==="use-credentials"?o.credentials="include":i.crossOrigin==="anonymous"?o.credentials="omit":o.credentials="same-origin",o}function r(i){if(i.ep)return;i.ep=!0;const o=n(i);fetch(i.href,o)}})();function $y(t){return t&&t.__esModule&&Object.prototype.hasOwnProperty.call(t,"default")?t.default:t}var Kd={exports:{}},el={},qd={exports:{}},H={};/**
 * @license React
 * react.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var ms=Symbol.for("react.element"),by=Symbol.for("react.portal"),By=Symbol.for("react.fragment"),Hy=Symbol.for("react.strict_mode"),Wy=Symbol.for("react.profiler"),Gy=Symbol.for("react.provider"),Ky=Symbol.for("react.context"),qy=Symbol.for("react.forward_ref"),Xy=Symbol.for("react.suspense"),Jy=Symbol.for("react.memo"),Qy=Symbol.for("react.lazy"),zh=Symbol.iterator;function Yy(t){return t===null||typeof t!="object"?null:(t=zh&&t[zh]||t["@@iterator"],typeof t=="function"?t:null)}var Xd={isMounted:function(){return!1},enqueueForceUpdate:function(){},enqueueReplaceState:function(){},enqueueSetState:function(){}},Jd=Object.assign,Qd={};function Xr(t,e,n){this.props=t,this.context=e,this.refs=Qd,this.updater=n||Xd}Xr.prototype.isReactComponent={};Xr.prototype.setState=function(t,e){if(typeof t!="object"&&typeof t!="function"&&t!=null)throw Error("setState(...): takes an object of state variables to update or a function which returns an object of state variables.");this.updater.enqueueSetState(this,t,e,"setState")};Xr.prototype.forceUpdate=function(t){this.updater.enqueueForceUpdate(this,t,"forceUpdate")};function Yd(){}Yd.prototype=Xr.prototype;function Lu(t,e,n){this.props=t,this.context=e,this.refs=Qd,this.updater=n||Xd}var xu=Lu.prototype=new Yd;xu.constructor=Lu;Jd(xu,Xr.prototype);xu.isPureReactComponent=!0;var $h=Array.isArray,Zd=Object.prototype.hasOwnProperty,Mu={current:null},ep={key:!0,ref:!0,__self:!0,__source:!0};function tp(t,e,n){var r,i={},o=null,l=null;if(e!=null)for(r in e.ref!==void 0&&(l=e.ref),e.key!==void 0&&(o=""+e.key),e)Zd.call(e,r)&&!ep.hasOwnProperty(r)&&(i[r]=e[r]);var u=arguments.length-2;if(u===1)i.children=n;else if(1<u){for(var h=Array(u),d=0;d<u;d++)h[d]=arguments[d+2];i.children=h}if(t&&t.defaultProps)for(r in u=t.defaultProps,u)i[r]===void 0&&(i[r]=u[r]);return{$$typeof:ms,type:t,key:o,ref:l,props:i,_owner:Mu.current}}function Zy(t,e){return{$$typeof:ms,type:t.type,key:e,ref:t.ref,props:t.props,_owner:t._owner}}function Uu(t){return typeof t=="object"&&t!==null&&t.$$typeof===ms}function ev(t){var e={"=":"=0",":":"=2"};return"$"+t.replace(/[=:]/g,function(n){return e[n]})}var bh=/\/+/g;function Wl(t,e){return typeof t=="object"&&t!==null&&t.key!=null?ev(""+t.key):e.toString(36)}function ro(t,e,n,r,i){var o=typeof t;(o==="undefined"||o==="boolean")&&(t=null);var l=!1;if(t===null)l=!0;else switch(o){case"string":case"number":l=!0;break;case"object":switch(t.$$typeof){case ms:case by:l=!0}}if(l)return l=t,i=i(l),t=r===""?"."+Wl(l,0):r,$h(i)?(n="",t!=null&&(n=t.replace(bh,"$&/")+"/"),ro(i,e,n,"",function(d){return d})):i!=null&&(Uu(i)&&(i=Zy(i,n+(!i.key||l&&l.key===i.key?"":(""+i.key).replace(bh,"$&/")+"/")+t)),e.push(i)),1;if(l=0,r=r===""?".":r+":",$h(t))for(var u=0;u<t.length;u++){o=t[u];var h=r+Wl(o,u);l+=ro(o,e,n,h,i)}else if(h=Yy(t),typeof h=="function")for(t=h.call(t),u=0;!(o=t.next()).done;)o=o.value,h=r+Wl(o,u++),l+=ro(o,e,n,h,i);else if(o==="object")throw e=String(t),Error("Objects are not valid as a React child (found: "+(e==="[object Object]"?"object with keys {"+Object.keys(t).join(", ")+"}":e)+"). If you meant to render a collection of children, use an array instead.");return l}function Fs(t,e,n){if(t==null)return t;var r=[],i=0;return ro(t,r,"","",function(o){return e.call(n,o,i++)}),r}function tv(t){if(t._status===-1){var e=t._result;e=e(),e.then(function(n){(t._status===0||t._status===-1)&&(t._status=1,t._result=n)},function(n){(t._status===0||t._status===-1)&&(t._status=2,t._result=n)}),t._status===-1&&(t._status=0,t._result=e)}if(t._status===1)return t._result.default;throw t._result}var Ue={current:null},io={transition:null},nv={ReactCurrentDispatcher:Ue,ReactCurrentBatchConfig:io,ReactCurrentOwner:Mu};function np(){throw Error("act(...) is not supported in production builds of React.")}H.Children={map:Fs,forEach:function(t,e,n){Fs(t,function(){e.apply(this,arguments)},n)},count:function(t){var e=0;return Fs(t,function(){e++}),e},toArray:function(t){return Fs(t,function(e){return e})||[]},only:function(t){if(!Uu(t))throw Error("React.Children.only expected to receive a single React element child.");return t}};H.Component=Xr;H.Fragment=By;H.Profiler=Wy;H.PureComponent=Lu;H.StrictMode=Hy;H.Suspense=Xy;H.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED=nv;H.act=np;H.cloneElement=function(t,e,n){if(t==null)throw Error("React.cloneElement(...): The argument must be a React element, but you passed "+t+".");var r=Jd({},t.props),i=t.key,o=t.ref,l=t._owner;if(e!=null){if(e.ref!==void 0&&(o=e.ref,l=Mu.current),e.key!==void 0&&(i=""+e.key),t.type&&t.type.defaultProps)var u=t.type.defaultProps;for(h in e)Zd.call(e,h)&&!ep.hasOwnProperty(h)&&(r[h]=e[h]===void 0&&u!==void 0?u[h]:e[h])}var h=arguments.length-2;if(h===1)r.children=n;else if(1<h){u=Array(h);for(var d=0;d<h;d++)u[d]=arguments[d+2];r.children=u}return{$$typeof:ms,type:t.type,key:i,ref:o,props:r,_owner:l}};H.createContext=function(t){return t={$$typeof:Ky,_currentValue:t,_currentValue2:t,_threadCount:0,Provider:null,Consumer:null,_defaultValue:null,_globalName:null},t.Provider={$$typeof:Gy,_context:t},t.Consumer=t};H.createElement=tp;H.createFactory=function(t){var e=tp.bind(null,t);return e.type=t,e};H.createRef=function(){return{current:null}};H.forwardRef=function(t){return{$$typeof:qy,render:t}};H.isValidElement=Uu;H.lazy=function(t){return{$$typeof:Qy,_payload:{_status:-1,_result:t},_init:tv}};H.memo=function(t,e){return{$$typeof:Jy,type:t,compare:e===void 0?null:e}};H.startTransition=function(t){var e=io.transition;io.transition={};try{t()}finally{io.transition=e}};H.unstable_act=np;H.useCallback=function(t,e){return Ue.current.useCallback(t,e)};H.useContext=function(t){return Ue.current.useContext(t)};H.useDebugValue=function(){};H.useDeferredValue=function(t){return Ue.current.useDeferredValue(t)};H.useEffect=function(t,e){return Ue.current.useEffect(t,e)};H.useId=function(){return Ue.current.useId()};H.useImperativeHandle=function(t,e,n){return Ue.current.useImperativeHandle(t,e,n)};H.useInsertionEffect=function(t,e){return Ue.current.useInsertionEffect(t,e)};H.useLayoutEffect=function(t,e){return Ue.current.useLayoutEffect(t,e)};H.useMemo=function(t,e){return Ue.current.useMemo(t,e)};H.useReducer=function(t,e,n){return Ue.current.useReducer(t,e,n)};H.useRef=function(t){return Ue.current.useRef(t)};H.useState=function(t){return Ue.current.useState(t)};H.useSyncExternalStore=function(t,e,n){return Ue.current.useSyncExternalStore(t,e,n)};H.useTransition=function(){return Ue.current.useTransition()};H.version="18.3.1";qd.exports=H;var X=qd.exports;const rp=$y(X),TI=zy({__proto__:null,default:rp},[X]);/**
 * @license React
 * react-jsx-runtime.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var rv=X,iv=Symbol.for("react.element"),sv=Symbol.for("react.fragment"),ov=Object.prototype.hasOwnProperty,lv=rv.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED.ReactCurrentOwner,av={key:!0,ref:!0,__self:!0,__source:!0};function ip(t,e,n){var r,i={},o=null,l=null;n!==void 0&&(o=""+n),e.key!==void 0&&(o=""+e.key),e.ref!==void 0&&(l=e.ref);for(r in e)ov.call(e,r)&&!av.hasOwnProperty(r)&&(i[r]=e[r]);if(t&&t.defaultProps)for(r in e=t.defaultProps,e)i[r]===void 0&&(i[r]=e[r]);return{$$typeof:iv,type:t,key:o,ref:l,props:i,_owner:lv.current}}el.Fragment=sv;el.jsx=ip;el.jsxs=ip;Kd.exports=el;var Pe=Kd.exports,Ra={},sp={exports:{}},qe={},op={exports:{}},lp={};/**
 * @license React
 * scheduler.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */(function(t){function e(F,$){var b=F.length;F.push($);e:for(;0<b;){var re=b-1>>>1,ue=F[re];if(0<i(ue,$))F[re]=$,F[b]=ue,b=re;else break e}}function n(F){return F.length===0?null:F[0]}function r(F){if(F.length===0)return null;var $=F[0],b=F.pop();if(b!==$){F[0]=b;e:for(var re=0,ue=F.length,Mn=ue>>>1;re<Mn;){var Je=2*(re+1)-1,Un=F[Je],it=Je+1,Qt=F[it];if(0>i(Un,b))it<ue&&0>i(Qt,Un)?(F[re]=Qt,F[it]=b,re=it):(F[re]=Un,F[Je]=b,re=Je);else if(it<ue&&0>i(Qt,b))F[re]=Qt,F[it]=b,re=it;else break e}}return $}function i(F,$){var b=F.sortIndex-$.sortIndex;return b!==0?b:F.id-$.id}if(typeof performance=="object"&&typeof performance.now=="function"){var o=performance;t.unstable_now=function(){return o.now()}}else{var l=Date,u=l.now();t.unstable_now=function(){return l.now()-u}}var h=[],d=[],k=1,S=null,E=3,N=!1,O=!1,L=!1,z=typeof setTimeout=="function"?setTimeout:null,I=typeof clearTimeout=="function"?clearTimeout:null,_=typeof setImmediate<"u"?setImmediate:null;typeof navigator<"u"&&navigator.scheduling!==void 0&&navigator.scheduling.isInputPending!==void 0&&navigator.scheduling.isInputPending.bind(navigator.scheduling);function T(F){for(var $=n(d);$!==null;){if($.callback===null)r(d);else if($.startTime<=F)r(d),$.sortIndex=$.expirationTime,e(h,$);else break;$=n(d)}}function R(F){if(L=!1,T(F),!O)if(n(h)!==null)O=!0,ni(M);else{var $=n(d);$!==null&&ri(R,$.startTime-F)}}function M(F,$){O=!1,L&&(L=!1,I(p),p=-1),N=!0;var b=E;try{for(T($),S=n(h);S!==null&&(!(S.expirationTime>$)||F&&!w());){var re=S.callback;if(typeof re=="function"){S.callback=null,E=S.priorityLevel;var ue=re(S.expirationTime<=$);$=t.unstable_now(),typeof ue=="function"?S.callback=ue:S===n(h)&&r(h),T($)}else r(h);S=n(h)}if(S!==null)var Mn=!0;else{var Je=n(d);Je!==null&&ri(R,Je.startTime-$),Mn=!1}return Mn}finally{S=null,E=b,N=!1}}var U=!1,g=null,p=-1,m=5,v=-1;function w(){return!(t.unstable_now()-v<m)}function C(){if(g!==null){var F=t.unstable_now();v=F;var $=!0;try{$=g(!0,F)}finally{$?y():(U=!1,g=null)}}else U=!1}var y;if(typeof _=="function")y=function(){_(C)};else if(typeof MessageChannel<"u"){var we=new MessageChannel,Rt=we.port2;we.port1.onmessage=C,y=function(){Rt.postMessage(null)}}else y=function(){z(C,0)};function ni(F){g=F,U||(U=!0,y())}function ri(F,$){p=z(function(){F(t.unstable_now())},$)}t.unstable_IdlePriority=5,t.unstable_ImmediatePriority=1,t.unstable_LowPriority=4,t.unstable_NormalPriority=3,t.unstable_Profiling=null,t.unstable_UserBlockingPriority=2,t.unstable_cancelCallback=function(F){F.callback=null},t.unstable_continueExecution=function(){O||N||(O=!0,ni(M))},t.unstable_forceFrameRate=function(F){0>F||125<F?console.error("forceFrameRate takes a positive int between 0 and 125, forcing frame rates higher than 125 fps is not supported"):m=0<F?Math.floor(1e3/F):5},t.unstable_getCurrentPriorityLevel=function(){return E},t.unstable_getFirstCallbackNode=function(){return n(h)},t.unstable_next=function(F){switch(E){case 1:case 2:case 3:var $=3;break;default:$=E}var b=E;E=$;try{return F()}finally{E=b}},t.unstable_pauseExecution=function(){},t.unstable_requestPaint=function(){},t.unstable_runWithPriority=function(F,$){switch(F){case 1:case 2:case 3:case 4:case 5:break;default:F=3}var b=E;E=F;try{return $()}finally{E=b}},t.unstable_scheduleCallback=function(F,$,b){var re=t.unstable_now();switch(typeof b=="object"&&b!==null?(b=b.delay,b=typeof b=="number"&&0<b?re+b:re):b=re,F){case 1:var ue=-1;break;case 2:ue=250;break;case 5:ue=1073741823;break;case 4:ue=1e4;break;default:ue=5e3}return ue=b+ue,F={id:k++,callback:$,priorityLevel:F,startTime:b,expirationTime:ue,sortIndex:-1},b>re?(F.sortIndex=b,e(d,F),n(h)===null&&F===n(d)&&(L?(I(p),p=-1):L=!0,ri(R,b-re))):(F.sortIndex=ue,e(h,F),O||N||(O=!0,ni(M))),F},t.unstable_shouldYield=w,t.unstable_wrapCallback=function(F){var $=E;return function(){var b=E;E=$;try{return F.apply(this,arguments)}finally{E=b}}}})(lp);op.exports=lp;var uv=op.exports;/**
 * @license React
 * react-dom.production.min.js
 *
 * Copyright (c) Facebook, Inc. and its affiliates.
 *
 * This source code is licensed under the MIT license found in the
 * LICENSE file in the root directory of this source tree.
 */var cv=X,Ke=uv;function D(t){for(var e="https://reactjs.org/docs/error-decoder.html?invariant="+t,n=1;n<arguments.length;n++)e+="&args[]="+encodeURIComponent(arguments[n]);return"Minified React error #"+t+"; visit "+e+" for the full message or use the non-minified dev environment for full errors and additional helpful warnings."}var ap=new Set,Xi={};function ar(t,e){Vr(t,e),Vr(t+"Capture",e)}function Vr(t,e){for(Xi[t]=e,t=0;t<e.length;t++)ap.add(e[t])}var $t=!(typeof window>"u"||typeof window.document>"u"||typeof window.document.createElement>"u"),Na=Object.prototype.hasOwnProperty,hv=/^[:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD][:A-Z_a-z\u00C0-\u00D6\u00D8-\u00F6\u00F8-\u02FF\u0370-\u037D\u037F-\u1FFF\u200C-\u200D\u2070-\u218F\u2C00-\u2FEF\u3001-\uD7FF\uF900-\uFDCF\uFDF0-\uFFFD\-.0-9\u00B7\u0300-\u036F\u203F-\u2040]*$/,Bh={},Hh={};function fv(t){return Na.call(Hh,t)?!0:Na.call(Bh,t)?!1:hv.test(t)?Hh[t]=!0:(Bh[t]=!0,!1)}function dv(t,e,n,r){if(n!==null&&n.type===0)return!1;switch(typeof e){case"function":case"symbol":return!0;case"boolean":return r?!1:n!==null?!n.acceptsBooleans:(t=t.toLowerCase().slice(0,5),t!=="data-"&&t!=="aria-");default:return!1}}function pv(t,e,n,r){if(e===null||typeof e>"u"||dv(t,e,n,r))return!0;if(r)return!1;if(n!==null)switch(n.type){case 3:return!e;case 4:return e===!1;case 5:return isNaN(e);case 6:return isNaN(e)||1>e}return!1}function Fe(t,e,n,r,i,o,l){this.acceptsBooleans=e===2||e===3||e===4,this.attributeName=r,this.attributeNamespace=i,this.mustUseProperty=n,this.propertyName=t,this.type=e,this.sanitizeURL=o,this.removeEmptyString=l}var Ie={};"children dangerouslySetInnerHTML defaultValue defaultChecked innerHTML suppressContentEditableWarning suppressHydrationWarning style".split(" ").forEach(function(t){Ie[t]=new Fe(t,0,!1,t,null,!1,!1)});[["acceptCharset","accept-charset"],["className","class"],["htmlFor","for"],["httpEquiv","http-equiv"]].forEach(function(t){var e=t[0];Ie[e]=new Fe(e,1,!1,t[1],null,!1,!1)});["contentEditable","draggable","spellCheck","value"].forEach(function(t){Ie[t]=new Fe(t,2,!1,t.toLowerCase(),null,!1,!1)});["autoReverse","externalResourcesRequired","focusable","preserveAlpha"].forEach(function(t){Ie[t]=new Fe(t,2,!1,t,null,!1,!1)});"allowFullScreen async autoFocus autoPlay controls default defer disabled disablePictureInPicture disableRemotePlayback formNoValidate hidden loop noModule noValidate open playsInline readOnly required reversed scoped seamless itemScope".split(" ").forEach(function(t){Ie[t]=new Fe(t,3,!1,t.toLowerCase(),null,!1,!1)});["checked","multiple","muted","selected"].forEach(function(t){Ie[t]=new Fe(t,3,!0,t,null,!1,!1)});["capture","download"].forEach(function(t){Ie[t]=new Fe(t,4,!1,t,null,!1,!1)});["cols","rows","size","span"].forEach(function(t){Ie[t]=new Fe(t,6,!1,t,null,!1,!1)});["rowSpan","start"].forEach(function(t){Ie[t]=new Fe(t,5,!1,t.toLowerCase(),null,!1,!1)});var Fu=/[\-:]([a-z])/g;function ju(t){return t[1].toUpperCase()}"accent-height alignment-baseline arabic-form baseline-shift cap-height clip-path clip-rule color-interpolation color-interpolation-filters color-profile color-rendering dominant-baseline enable-background fill-opacity fill-rule flood-color flood-opacity font-family font-size font-size-adjust font-stretch font-style font-variant font-weight glyph-name glyph-orientation-horizontal glyph-orientation-vertical horiz-adv-x horiz-origin-x image-rendering letter-spacing lighting-color marker-end marker-mid marker-start overline-position overline-thickness paint-order panose-1 pointer-events rendering-intent shape-rendering stop-color stop-opacity strikethrough-position strikethrough-thickness stroke-dasharray stroke-dashoffset stroke-linecap stroke-linejoin stroke-miterlimit stroke-opacity stroke-width text-anchor text-decoration text-rendering underline-position underline-thickness unicode-bidi unicode-range units-per-em v-alphabetic v-hanging v-ideographic v-mathematical vector-effect vert-adv-y vert-origin-x vert-origin-y word-spacing writing-mode xmlns:xlink x-height".split(" ").forEach(function(t){var e=t.replace(Fu,ju);Ie[e]=new Fe(e,1,!1,t,null,!1,!1)});"xlink:actuate xlink:arcrole xlink:role xlink:show xlink:title xlink:type".split(" ").forEach(function(t){var e=t.replace(Fu,ju);Ie[e]=new Fe(e,1,!1,t,"http://www.w3.org/1999/xlink",!1,!1)});["xml:base","xml:lang","xml:space"].forEach(function(t){var e=t.replace(Fu,ju);Ie[e]=new Fe(e,1,!1,t,"http://www.w3.org/XML/1998/namespace",!1,!1)});["tabIndex","crossOrigin"].forEach(function(t){Ie[t]=new Fe(t,1,!1,t.toLowerCase(),null,!1,!1)});Ie.xlinkHref=new Fe("xlinkHref",1,!1,"xlink:href","http://www.w3.org/1999/xlink",!0,!1);["src","href","action","formAction"].forEach(function(t){Ie[t]=new Fe(t,1,!1,t.toLowerCase(),null,!0,!0)});function Vu(t,e,n,r){var i=Ie.hasOwnProperty(e)?Ie[e]:null;(i!==null?i.type!==0:r||!(2<e.length)||e[0]!=="o"&&e[0]!=="O"||e[1]!=="n"&&e[1]!=="N")&&(pv(e,n,i,r)&&(n=null),r||i===null?fv(e)&&(n===null?t.removeAttribute(e):t.setAttribute(e,""+n)):i.mustUseProperty?t[i.propertyName]=n===null?i.type===3?!1:"":n:(e=i.attributeName,r=i.attributeNamespace,n===null?t.removeAttribute(e):(i=i.type,n=i===3||i===4&&n===!0?"":""+n,r?t.setAttributeNS(r,e,n):t.setAttribute(e,n))))}var Xt=cv.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED,js=Symbol.for("react.element"),mr=Symbol.for("react.portal"),yr=Symbol.for("react.fragment"),zu=Symbol.for("react.strict_mode"),Oa=Symbol.for("react.profiler"),up=Symbol.for("react.provider"),cp=Symbol.for("react.context"),$u=Symbol.for("react.forward_ref"),Da=Symbol.for("react.suspense"),La=Symbol.for("react.suspense_list"),bu=Symbol.for("react.memo"),ln=Symbol.for("react.lazy"),hp=Symbol.for("react.offscreen"),Wh=Symbol.iterator;function wi(t){return t===null||typeof t!="object"?null:(t=Wh&&t[Wh]||t["@@iterator"],typeof t=="function"?t:null)}var le=Object.assign,Gl;function Ai(t){if(Gl===void 0)try{throw Error()}catch(n){var e=n.stack.trim().match(/\n( *(at )?)/);Gl=e&&e[1]||""}return`
`+Gl+t}var Kl=!1;function ql(t,e){if(!t||Kl)return"";Kl=!0;var n=Error.prepareStackTrace;Error.prepareStackTrace=void 0;try{if(e)if(e=function(){throw Error()},Object.defineProperty(e.prototype,"props",{set:function(){throw Error()}}),typeof Reflect=="object"&&Reflect.construct){try{Reflect.construct(e,[])}catch(d){var r=d}Reflect.construct(t,[],e)}else{try{e.call()}catch(d){r=d}t.call(e.prototype)}else{try{throw Error()}catch(d){r=d}t()}}catch(d){if(d&&r&&typeof d.stack=="string"){for(var i=d.stack.split(`
`),o=r.stack.split(`
`),l=i.length-1,u=o.length-1;1<=l&&0<=u&&i[l]!==o[u];)u--;for(;1<=l&&0<=u;l--,u--)if(i[l]!==o[u]){if(l!==1||u!==1)do if(l--,u--,0>u||i[l]!==o[u]){var h=`
`+i[l].replace(" at new "," at ");return t.displayName&&h.includes("<anonymous>")&&(h=h.replace("<anonymous>",t.displayName)),h}while(1<=l&&0<=u);break}}}finally{Kl=!1,Error.prepareStackTrace=n}return(t=t?t.displayName||t.name:"")?Ai(t):""}function gv(t){switch(t.tag){case 5:return Ai(t.type);case 16:return Ai("Lazy");case 13:return Ai("Suspense");case 19:return Ai("SuspenseList");case 0:case 2:case 15:return t=ql(t.type,!1),t;case 11:return t=ql(t.type.render,!1),t;case 1:return t=ql(t.type,!0),t;default:return""}}function xa(t){if(t==null)return null;if(typeof t=="function")return t.displayName||t.name||null;if(typeof t=="string")return t;switch(t){case yr:return"Fragment";case mr:return"Portal";case Oa:return"Profiler";case zu:return"StrictMode";case Da:return"Suspense";case La:return"SuspenseList"}if(typeof t=="object")switch(t.$$typeof){case cp:return(t.displayName||"Context")+".Consumer";case up:return(t._context.displayName||"Context")+".Provider";case $u:var e=t.render;return t=t.displayName,t||(t=e.displayName||e.name||"",t=t!==""?"ForwardRef("+t+")":"ForwardRef"),t;case bu:return e=t.displayName||null,e!==null?e:xa(t.type)||"Memo";case ln:e=t._payload,t=t._init;try{return xa(t(e))}catch{}}return null}function mv(t){var e=t.type;switch(t.tag){case 24:return"Cache";case 9:return(e.displayName||"Context")+".Consumer";case 10:return(e._context.displayName||"Context")+".Provider";case 18:return"DehydratedFragment";case 11:return t=e.render,t=t.displayName||t.name||"",e.displayName||(t!==""?"ForwardRef("+t+")":"ForwardRef");case 7:return"Fragment";case 5:return e;case 4:return"Portal";case 3:return"Root";case 6:return"Text";case 16:return xa(e);case 8:return e===zu?"StrictMode":"Mode";case 22:return"Offscreen";case 12:return"Profiler";case 21:return"Scope";case 13:return"Suspense";case 19:return"SuspenseList";case 25:return"TracingMarker";case 1:case 0:case 17:case 2:case 14:case 15:if(typeof e=="function")return e.displayName||e.name||null;if(typeof e=="string")return e}return null}function Pn(t){switch(typeof t){case"boolean":case"number":case"string":case"undefined":return t;case"object":return t;default:return""}}function fp(t){var e=t.type;return(t=t.nodeName)&&t.toLowerCase()==="input"&&(e==="checkbox"||e==="radio")}function yv(t){var e=fp(t)?"checked":"value",n=Object.getOwnPropertyDescriptor(t.constructor.prototype,e),r=""+t[e];if(!t.hasOwnProperty(e)&&typeof n<"u"&&typeof n.get=="function"&&typeof n.set=="function"){var i=n.get,o=n.set;return Object.defineProperty(t,e,{configurable:!0,get:function(){return i.call(this)},set:function(l){r=""+l,o.call(this,l)}}),Object.defineProperty(t,e,{enumerable:n.enumerable}),{getValue:function(){return r},setValue:function(l){r=""+l},stopTracking:function(){t._valueTracker=null,delete t[e]}}}}function Vs(t){t._valueTracker||(t._valueTracker=yv(t))}function dp(t){if(!t)return!1;var e=t._valueTracker;if(!e)return!0;var n=e.getValue(),r="";return t&&(r=fp(t)?t.checked?"true":"false":t.value),t=r,t!==n?(e.setValue(t),!0):!1}function Eo(t){if(t=t||(typeof document<"u"?document:void 0),typeof t>"u")return null;try{return t.activeElement||t.body}catch{return t.body}}function Ma(t,e){var n=e.checked;return le({},e,{defaultChecked:void 0,defaultValue:void 0,value:void 0,checked:n??t._wrapperState.initialChecked})}function Gh(t,e){var n=e.defaultValue==null?"":e.defaultValue,r=e.checked!=null?e.checked:e.defaultChecked;n=Pn(e.value!=null?e.value:n),t._wrapperState={initialChecked:r,initialValue:n,controlled:e.type==="checkbox"||e.type==="radio"?e.checked!=null:e.value!=null}}function pp(t,e){e=e.checked,e!=null&&Vu(t,"checked",e,!1)}function Ua(t,e){pp(t,e);var n=Pn(e.value),r=e.type;if(n!=null)r==="number"?(n===0&&t.value===""||t.value!=n)&&(t.value=""+n):t.value!==""+n&&(t.value=""+n);else if(r==="submit"||r==="reset"){t.removeAttribute("value");return}e.hasOwnProperty("value")?Fa(t,e.type,n):e.hasOwnProperty("defaultValue")&&Fa(t,e.type,Pn(e.defaultValue)),e.checked==null&&e.defaultChecked!=null&&(t.defaultChecked=!!e.defaultChecked)}function Kh(t,e,n){if(e.hasOwnProperty("value")||e.hasOwnProperty("defaultValue")){var r=e.type;if(!(r!=="submit"&&r!=="reset"||e.value!==void 0&&e.value!==null))return;e=""+t._wrapperState.initialValue,n||e===t.value||(t.value=e),t.defaultValue=e}n=t.name,n!==""&&(t.name=""),t.defaultChecked=!!t._wrapperState.initialChecked,n!==""&&(t.name=n)}function Fa(t,e,n){(e!=="number"||Eo(t.ownerDocument)!==t)&&(n==null?t.defaultValue=""+t._wrapperState.initialValue:t.defaultValue!==""+n&&(t.defaultValue=""+n))}var Ri=Array.isArray;function Rr(t,e,n,r){if(t=t.options,e){e={};for(var i=0;i<n.length;i++)e["$"+n[i]]=!0;for(n=0;n<t.length;n++)i=e.hasOwnProperty("$"+t[n].value),t[n].selected!==i&&(t[n].selected=i),i&&r&&(t[n].defaultSelected=!0)}else{for(n=""+Pn(n),e=null,i=0;i<t.length;i++){if(t[i].value===n){t[i].selected=!0,r&&(t[i].defaultSelected=!0);return}e!==null||t[i].disabled||(e=t[i])}e!==null&&(e.selected=!0)}}function ja(t,e){if(e.dangerouslySetInnerHTML!=null)throw Error(D(91));return le({},e,{value:void 0,defaultValue:void 0,children:""+t._wrapperState.initialValue})}function qh(t,e){var n=e.value;if(n==null){if(n=e.children,e=e.defaultValue,n!=null){if(e!=null)throw Error(D(92));if(Ri(n)){if(1<n.length)throw Error(D(93));n=n[0]}e=n}e==null&&(e=""),n=e}t._wrapperState={initialValue:Pn(n)}}function gp(t,e){var n=Pn(e.value),r=Pn(e.defaultValue);n!=null&&(n=""+n,n!==t.value&&(t.value=n),e.defaultValue==null&&t.defaultValue!==n&&(t.defaultValue=n)),r!=null&&(t.defaultValue=""+r)}function Xh(t){var e=t.textContent;e===t._wrapperState.initialValue&&e!==""&&e!==null&&(t.value=e)}function mp(t){switch(t){case"svg":return"http://www.w3.org/2000/svg";case"math":return"http://www.w3.org/1998/Math/MathML";default:return"http://www.w3.org/1999/xhtml"}}function Va(t,e){return t==null||t==="http://www.w3.org/1999/xhtml"?mp(e):t==="http://www.w3.org/2000/svg"&&e==="foreignObject"?"http://www.w3.org/1999/xhtml":t}var zs,yp=function(t){return typeof MSApp<"u"&&MSApp.execUnsafeLocalFunction?function(e,n,r,i){MSApp.execUnsafeLocalFunction(function(){return t(e,n,r,i)})}:t}(function(t,e){if(t.namespaceURI!=="http://www.w3.org/2000/svg"||"innerHTML"in t)t.innerHTML=e;else{for(zs=zs||document.createElement("div"),zs.innerHTML="<svg>"+e.valueOf().toString()+"</svg>",e=zs.firstChild;t.firstChild;)t.removeChild(t.firstChild);for(;e.firstChild;)t.appendChild(e.firstChild)}});function Ji(t,e){if(e){var n=t.firstChild;if(n&&n===t.lastChild&&n.nodeType===3){n.nodeValue=e;return}}t.textContent=e}var xi={animationIterationCount:!0,aspectRatio:!0,borderImageOutset:!0,borderImageSlice:!0,borderImageWidth:!0,boxFlex:!0,boxFlexGroup:!0,boxOrdinalGroup:!0,columnCount:!0,columns:!0,flex:!0,flexGrow:!0,flexPositive:!0,flexShrink:!0,flexNegative:!0,flexOrder:!0,gridArea:!0,gridRow:!0,gridRowEnd:!0,gridRowSpan:!0,gridRowStart:!0,gridColumn:!0,gridColumnEnd:!0,gridColumnSpan:!0,gridColumnStart:!0,fontWeight:!0,lineClamp:!0,lineHeight:!0,opacity:!0,order:!0,orphans:!0,tabSize:!0,widows:!0,zIndex:!0,zoom:!0,fillOpacity:!0,floodOpacity:!0,stopOpacity:!0,strokeDasharray:!0,strokeDashoffset:!0,strokeMiterlimit:!0,strokeOpacity:!0,strokeWidth:!0},vv=["Webkit","ms","Moz","O"];Object.keys(xi).forEach(function(t){vv.forEach(function(e){e=e+t.charAt(0).toUpperCase()+t.substring(1),xi[e]=xi[t]})});function vp(t,e,n){return e==null||typeof e=="boolean"||e===""?"":n||typeof e!="number"||e===0||xi.hasOwnProperty(t)&&xi[t]?(""+e).trim():e+"px"}function _p(t,e){t=t.style;for(var n in e)if(e.hasOwnProperty(n)){var r=n.indexOf("--")===0,i=vp(n,e[n],r);n==="float"&&(n="cssFloat"),r?t.setProperty(n,i):t[n]=i}}var _v=le({menuitem:!0},{area:!0,base:!0,br:!0,col:!0,embed:!0,hr:!0,img:!0,input:!0,keygen:!0,link:!0,meta:!0,param:!0,source:!0,track:!0,wbr:!0});function za(t,e){if(e){if(_v[t]&&(e.children!=null||e.dangerouslySetInnerHTML!=null))throw Error(D(137,t));if(e.dangerouslySetInnerHTML!=null){if(e.children!=null)throw Error(D(60));if(typeof e.dangerouslySetInnerHTML!="object"||!("__html"in e.dangerouslySetInnerHTML))throw Error(D(61))}if(e.style!=null&&typeof e.style!="object")throw Error(D(62))}}function $a(t,e){if(t.indexOf("-")===-1)return typeof e.is=="string";switch(t){case"annotation-xml":case"color-profile":case"font-face":case"font-face-src":case"font-face-uri":case"font-face-format":case"font-face-name":case"missing-glyph":return!1;default:return!0}}var ba=null;function Bu(t){return t=t.target||t.srcElement||window,t.correspondingUseElement&&(t=t.correspondingUseElement),t.nodeType===3?t.parentNode:t}var Ba=null,Nr=null,Or=null;function Jh(t){if(t=_s(t)){if(typeof Ba!="function")throw Error(D(280));var e=t.stateNode;e&&(e=sl(e),Ba(t.stateNode,t.type,e))}}function wp(t){Nr?Or?Or.push(t):Or=[t]:Nr=t}function Ep(){if(Nr){var t=Nr,e=Or;if(Or=Nr=null,Jh(t),e)for(t=0;t<e.length;t++)Jh(e[t])}}function Sp(t,e){return t(e)}function Ip(){}var Xl=!1;function Tp(t,e,n){if(Xl)return t(e,n);Xl=!0;try{return Sp(t,e,n)}finally{Xl=!1,(Nr!==null||Or!==null)&&(Ip(),Ep())}}function Qi(t,e){var n=t.stateNode;if(n===null)return null;var r=sl(n);if(r===null)return null;n=r[e];e:switch(e){case"onClick":case"onClickCapture":case"onDoubleClick":case"onDoubleClickCapture":case"onMouseDown":case"onMouseDownCapture":case"onMouseMove":case"onMouseMoveCapture":case"onMouseUp":case"onMouseUpCapture":case"onMouseEnter":(r=!r.disabled)||(t=t.type,r=!(t==="button"||t==="input"||t==="select"||t==="textarea")),t=!r;break e;default:t=!1}if(t)return null;if(n&&typeof n!="function")throw Error(D(231,e,typeof n));return n}var Ha=!1;if($t)try{var Ei={};Object.defineProperty(Ei,"passive",{get:function(){Ha=!0}}),window.addEventListener("test",Ei,Ei),window.removeEventListener("test",Ei,Ei)}catch{Ha=!1}function wv(t,e,n,r,i,o,l,u,h){var d=Array.prototype.slice.call(arguments,3);try{e.apply(n,d)}catch(k){this.onError(k)}}var Mi=!1,So=null,Io=!1,Wa=null,Ev={onError:function(t){Mi=!0,So=t}};function Sv(t,e,n,r,i,o,l,u,h){Mi=!1,So=null,wv.apply(Ev,arguments)}function Iv(t,e,n,r,i,o,l,u,h){if(Sv.apply(this,arguments),Mi){if(Mi){var d=So;Mi=!1,So=null}else throw Error(D(198));Io||(Io=!0,Wa=d)}}function ur(t){var e=t,n=t;if(t.alternate)for(;e.return;)e=e.return;else{t=e;do e=t,e.flags&4098&&(n=e.return),t=e.return;while(t)}return e.tag===3?n:null}function kp(t){if(t.tag===13){var e=t.memoizedState;if(e===null&&(t=t.alternate,t!==null&&(e=t.memoizedState)),e!==null)return e.dehydrated}return null}function Qh(t){if(ur(t)!==t)throw Error(D(188))}function Tv(t){var e=t.alternate;if(!e){if(e=ur(t),e===null)throw Error(D(188));return e!==t?null:t}for(var n=t,r=e;;){var i=n.return;if(i===null)break;var o=i.alternate;if(o===null){if(r=i.return,r!==null){n=r;continue}break}if(i.child===o.child){for(o=i.child;o;){if(o===n)return Qh(i),t;if(o===r)return Qh(i),e;o=o.sibling}throw Error(D(188))}if(n.return!==r.return)n=i,r=o;else{for(var l=!1,u=i.child;u;){if(u===n){l=!0,n=i,r=o;break}if(u===r){l=!0,r=i,n=o;break}u=u.sibling}if(!l){for(u=o.child;u;){if(u===n){l=!0,n=o,r=i;break}if(u===r){l=!0,r=o,n=i;break}u=u.sibling}if(!l)throw Error(D(189))}}if(n.alternate!==r)throw Error(D(190))}if(n.tag!==3)throw Error(D(188));return n.stateNode.current===n?t:e}function Cp(t){return t=Tv(t),t!==null?Pp(t):null}function Pp(t){if(t.tag===5||t.tag===6)return t;for(t=t.child;t!==null;){var e=Pp(t);if(e!==null)return e;t=t.sibling}return null}var Ap=Ke.unstable_scheduleCallback,Yh=Ke.unstable_cancelCallback,kv=Ke.unstable_shouldYield,Cv=Ke.unstable_requestPaint,he=Ke.unstable_now,Pv=Ke.unstable_getCurrentPriorityLevel,Hu=Ke.unstable_ImmediatePriority,Rp=Ke.unstable_UserBlockingPriority,To=Ke.unstable_NormalPriority,Av=Ke.unstable_LowPriority,Np=Ke.unstable_IdlePriority,tl=null,kt=null;function Rv(t){if(kt&&typeof kt.onCommitFiberRoot=="function")try{kt.onCommitFiberRoot(tl,t,void 0,(t.current.flags&128)===128)}catch{}}var ft=Math.clz32?Math.clz32:Dv,Nv=Math.log,Ov=Math.LN2;function Dv(t){return t>>>=0,t===0?32:31-(Nv(t)/Ov|0)|0}var $s=64,bs=4194304;function Ni(t){switch(t&-t){case 1:return 1;case 2:return 2;case 4:return 4;case 8:return 8;case 16:return 16;case 32:return 32;case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:return t&4194240;case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:return t&130023424;case 134217728:return 134217728;case 268435456:return 268435456;case 536870912:return 536870912;case 1073741824:return 1073741824;default:return t}}function ko(t,e){var n=t.pendingLanes;if(n===0)return 0;var r=0,i=t.suspendedLanes,o=t.pingedLanes,l=n&268435455;if(l!==0){var u=l&~i;u!==0?r=Ni(u):(o&=l,o!==0&&(r=Ni(o)))}else l=n&~i,l!==0?r=Ni(l):o!==0&&(r=Ni(o));if(r===0)return 0;if(e!==0&&e!==r&&!(e&i)&&(i=r&-r,o=e&-e,i>=o||i===16&&(o&4194240)!==0))return e;if(r&4&&(r|=n&16),e=t.entangledLanes,e!==0)for(t=t.entanglements,e&=r;0<e;)n=31-ft(e),i=1<<n,r|=t[n],e&=~i;return r}function Lv(t,e){switch(t){case 1:case 2:case 4:return e+250;case 8:case 16:case 32:case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:return e+5e3;case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:return-1;case 134217728:case 268435456:case 536870912:case 1073741824:return-1;default:return-1}}function xv(t,e){for(var n=t.suspendedLanes,r=t.pingedLanes,i=t.expirationTimes,o=t.pendingLanes;0<o;){var l=31-ft(o),u=1<<l,h=i[l];h===-1?(!(u&n)||u&r)&&(i[l]=Lv(u,e)):h<=e&&(t.expiredLanes|=u),o&=~u}}function Ga(t){return t=t.pendingLanes&-1073741825,t!==0?t:t&1073741824?1073741824:0}function Op(){var t=$s;return $s<<=1,!($s&4194240)&&($s=64),t}function Jl(t){for(var e=[],n=0;31>n;n++)e.push(t);return e}function ys(t,e,n){t.pendingLanes|=e,e!==536870912&&(t.suspendedLanes=0,t.pingedLanes=0),t=t.eventTimes,e=31-ft(e),t[e]=n}function Mv(t,e){var n=t.pendingLanes&~e;t.pendingLanes=e,t.suspendedLanes=0,t.pingedLanes=0,t.expiredLanes&=e,t.mutableReadLanes&=e,t.entangledLanes&=e,e=t.entanglements;var r=t.eventTimes;for(t=t.expirationTimes;0<n;){var i=31-ft(n),o=1<<i;e[i]=0,r[i]=-1,t[i]=-1,n&=~o}}function Wu(t,e){var n=t.entangledLanes|=e;for(t=t.entanglements;n;){var r=31-ft(n),i=1<<r;i&e|t[r]&e&&(t[r]|=e),n&=~i}}var Q=0;function Dp(t){return t&=-t,1<t?4<t?t&268435455?16:536870912:4:1}var Lp,Gu,xp,Mp,Up,Ka=!1,Bs=[],mn=null,yn=null,vn=null,Yi=new Map,Zi=new Map,un=[],Uv="mousedown mouseup touchcancel touchend touchstart auxclick dblclick pointercancel pointerdown pointerup dragend dragstart drop compositionend compositionstart keydown keypress keyup input textInput copy cut paste click change contextmenu reset submit".split(" ");function Zh(t,e){switch(t){case"focusin":case"focusout":mn=null;break;case"dragenter":case"dragleave":yn=null;break;case"mouseover":case"mouseout":vn=null;break;case"pointerover":case"pointerout":Yi.delete(e.pointerId);break;case"gotpointercapture":case"lostpointercapture":Zi.delete(e.pointerId)}}function Si(t,e,n,r,i,o){return t===null||t.nativeEvent!==o?(t={blockedOn:e,domEventName:n,eventSystemFlags:r,nativeEvent:o,targetContainers:[i]},e!==null&&(e=_s(e),e!==null&&Gu(e)),t):(t.eventSystemFlags|=r,e=t.targetContainers,i!==null&&e.indexOf(i)===-1&&e.push(i),t)}function Fv(t,e,n,r,i){switch(e){case"focusin":return mn=Si(mn,t,e,n,r,i),!0;case"dragenter":return yn=Si(yn,t,e,n,r,i),!0;case"mouseover":return vn=Si(vn,t,e,n,r,i),!0;case"pointerover":var o=i.pointerId;return Yi.set(o,Si(Yi.get(o)||null,t,e,n,r,i)),!0;case"gotpointercapture":return o=i.pointerId,Zi.set(o,Si(Zi.get(o)||null,t,e,n,r,i)),!0}return!1}function Fp(t){var e=Wn(t.target);if(e!==null){var n=ur(e);if(n!==null){if(e=n.tag,e===13){if(e=kp(n),e!==null){t.blockedOn=e,Up(t.priority,function(){xp(n)});return}}else if(e===3&&n.stateNode.current.memoizedState.isDehydrated){t.blockedOn=n.tag===3?n.stateNode.containerInfo:null;return}}}t.blockedOn=null}function so(t){if(t.blockedOn!==null)return!1;for(var e=t.targetContainers;0<e.length;){var n=qa(t.domEventName,t.eventSystemFlags,e[0],t.nativeEvent);if(n===null){n=t.nativeEvent;var r=new n.constructor(n.type,n);ba=r,n.target.dispatchEvent(r),ba=null}else return e=_s(n),e!==null&&Gu(e),t.blockedOn=n,!1;e.shift()}return!0}function ef(t,e,n){so(t)&&n.delete(e)}function jv(){Ka=!1,mn!==null&&so(mn)&&(mn=null),yn!==null&&so(yn)&&(yn=null),vn!==null&&so(vn)&&(vn=null),Yi.forEach(ef),Zi.forEach(ef)}function Ii(t,e){t.blockedOn===e&&(t.blockedOn=null,Ka||(Ka=!0,Ke.unstable_scheduleCallback(Ke.unstable_NormalPriority,jv)))}function es(t){function e(i){return Ii(i,t)}if(0<Bs.length){Ii(Bs[0],t);for(var n=1;n<Bs.length;n++){var r=Bs[n];r.blockedOn===t&&(r.blockedOn=null)}}for(mn!==null&&Ii(mn,t),yn!==null&&Ii(yn,t),vn!==null&&Ii(vn,t),Yi.forEach(e),Zi.forEach(e),n=0;n<un.length;n++)r=un[n],r.blockedOn===t&&(r.blockedOn=null);for(;0<un.length&&(n=un[0],n.blockedOn===null);)Fp(n),n.blockedOn===null&&un.shift()}var Dr=Xt.ReactCurrentBatchConfig,Co=!0;function Vv(t,e,n,r){var i=Q,o=Dr.transition;Dr.transition=null;try{Q=1,Ku(t,e,n,r)}finally{Q=i,Dr.transition=o}}function zv(t,e,n,r){var i=Q,o=Dr.transition;Dr.transition=null;try{Q=4,Ku(t,e,n,r)}finally{Q=i,Dr.transition=o}}function Ku(t,e,n,r){if(Co){var i=qa(t,e,n,r);if(i===null)oa(t,e,r,Po,n),Zh(t,r);else if(Fv(i,t,e,n,r))r.stopPropagation();else if(Zh(t,r),e&4&&-1<Uv.indexOf(t)){for(;i!==null;){var o=_s(i);if(o!==null&&Lp(o),o=qa(t,e,n,r),o===null&&oa(t,e,r,Po,n),o===i)break;i=o}i!==null&&r.stopPropagation()}else oa(t,e,r,null,n)}}var Po=null;function qa(t,e,n,r){if(Po=null,t=Bu(r),t=Wn(t),t!==null)if(e=ur(t),e===null)t=null;else if(n=e.tag,n===13){if(t=kp(e),t!==null)return t;t=null}else if(n===3){if(e.stateNode.current.memoizedState.isDehydrated)return e.tag===3?e.stateNode.containerInfo:null;t=null}else e!==t&&(t=null);return Po=t,null}function jp(t){switch(t){case"cancel":case"click":case"close":case"contextmenu":case"copy":case"cut":case"auxclick":case"dblclick":case"dragend":case"dragstart":case"drop":case"focusin":case"focusout":case"input":case"invalid":case"keydown":case"keypress":case"keyup":case"mousedown":case"mouseup":case"paste":case"pause":case"play":case"pointercancel":case"pointerdown":case"pointerup":case"ratechange":case"reset":case"resize":case"seeked":case"submit":case"touchcancel":case"touchend":case"touchstart":case"volumechange":case"change":case"selectionchange":case"textInput":case"compositionstart":case"compositionend":case"compositionupdate":case"beforeblur":case"afterblur":case"beforeinput":case"blur":case"fullscreenchange":case"focus":case"hashchange":case"popstate":case"select":case"selectstart":return 1;case"drag":case"dragenter":case"dragexit":case"dragleave":case"dragover":case"mousemove":case"mouseout":case"mouseover":case"pointermove":case"pointerout":case"pointerover":case"scroll":case"toggle":case"touchmove":case"wheel":case"mouseenter":case"mouseleave":case"pointerenter":case"pointerleave":return 4;case"message":switch(Pv()){case Hu:return 1;case Rp:return 4;case To:case Av:return 16;case Np:return 536870912;default:return 16}default:return 16}}var pn=null,qu=null,oo=null;function Vp(){if(oo)return oo;var t,e=qu,n=e.length,r,i="value"in pn?pn.value:pn.textContent,o=i.length;for(t=0;t<n&&e[t]===i[t];t++);var l=n-t;for(r=1;r<=l&&e[n-r]===i[o-r];r++);return oo=i.slice(t,1<r?1-r:void 0)}function lo(t){var e=t.keyCode;return"charCode"in t?(t=t.charCode,t===0&&e===13&&(t=13)):t=e,t===10&&(t=13),32<=t||t===13?t:0}function Hs(){return!0}function tf(){return!1}function Xe(t){function e(n,r,i,o,l){this._reactName=n,this._targetInst=i,this.type=r,this.nativeEvent=o,this.target=l,this.currentTarget=null;for(var u in t)t.hasOwnProperty(u)&&(n=t[u],this[u]=n?n(o):o[u]);return this.isDefaultPrevented=(o.defaultPrevented!=null?o.defaultPrevented:o.returnValue===!1)?Hs:tf,this.isPropagationStopped=tf,this}return le(e.prototype,{preventDefault:function(){this.defaultPrevented=!0;var n=this.nativeEvent;n&&(n.preventDefault?n.preventDefault():typeof n.returnValue!="unknown"&&(n.returnValue=!1),this.isDefaultPrevented=Hs)},stopPropagation:function(){var n=this.nativeEvent;n&&(n.stopPropagation?n.stopPropagation():typeof n.cancelBubble!="unknown"&&(n.cancelBubble=!0),this.isPropagationStopped=Hs)},persist:function(){},isPersistent:Hs}),e}var Jr={eventPhase:0,bubbles:0,cancelable:0,timeStamp:function(t){return t.timeStamp||Date.now()},defaultPrevented:0,isTrusted:0},Xu=Xe(Jr),vs=le({},Jr,{view:0,detail:0}),$v=Xe(vs),Ql,Yl,Ti,nl=le({},vs,{screenX:0,screenY:0,clientX:0,clientY:0,pageX:0,pageY:0,ctrlKey:0,shiftKey:0,altKey:0,metaKey:0,getModifierState:Ju,button:0,buttons:0,relatedTarget:function(t){return t.relatedTarget===void 0?t.fromElement===t.srcElement?t.toElement:t.fromElement:t.relatedTarget},movementX:function(t){return"movementX"in t?t.movementX:(t!==Ti&&(Ti&&t.type==="mousemove"?(Ql=t.screenX-Ti.screenX,Yl=t.screenY-Ti.screenY):Yl=Ql=0,Ti=t),Ql)},movementY:function(t){return"movementY"in t?t.movementY:Yl}}),nf=Xe(nl),bv=le({},nl,{dataTransfer:0}),Bv=Xe(bv),Hv=le({},vs,{relatedTarget:0}),Zl=Xe(Hv),Wv=le({},Jr,{animationName:0,elapsedTime:0,pseudoElement:0}),Gv=Xe(Wv),Kv=le({},Jr,{clipboardData:function(t){return"clipboardData"in t?t.clipboardData:window.clipboardData}}),qv=Xe(Kv),Xv=le({},Jr,{data:0}),rf=Xe(Xv),Jv={Esc:"Escape",Spacebar:" ",Left:"ArrowLeft",Up:"ArrowUp",Right:"ArrowRight",Down:"ArrowDown",Del:"Delete",Win:"OS",Menu:"ContextMenu",Apps:"ContextMenu",Scroll:"ScrollLock",MozPrintableKey:"Unidentified"},Qv={8:"Backspace",9:"Tab",12:"Clear",13:"Enter",16:"Shift",17:"Control",18:"Alt",19:"Pause",20:"CapsLock",27:"Escape",32:" ",33:"PageUp",34:"PageDown",35:"End",36:"Home",37:"ArrowLeft",38:"ArrowUp",39:"ArrowRight",40:"ArrowDown",45:"Insert",46:"Delete",112:"F1",113:"F2",114:"F3",115:"F4",116:"F5",117:"F6",118:"F7",119:"F8",120:"F9",121:"F10",122:"F11",123:"F12",144:"NumLock",145:"ScrollLock",224:"Meta"},Yv={Alt:"altKey",Control:"ctrlKey",Meta:"metaKey",Shift:"shiftKey"};function Zv(t){var e=this.nativeEvent;return e.getModifierState?e.getModifierState(t):(t=Yv[t])?!!e[t]:!1}function Ju(){return Zv}var e_=le({},vs,{key:function(t){if(t.key){var e=Jv[t.key]||t.key;if(e!=="Unidentified")return e}return t.type==="keypress"?(t=lo(t),t===13?"Enter":String.fromCharCode(t)):t.type==="keydown"||t.type==="keyup"?Qv[t.keyCode]||"Unidentified":""},code:0,location:0,ctrlKey:0,shiftKey:0,altKey:0,metaKey:0,repeat:0,locale:0,getModifierState:Ju,charCode:function(t){return t.type==="keypress"?lo(t):0},keyCode:function(t){return t.type==="keydown"||t.type==="keyup"?t.keyCode:0},which:function(t){return t.type==="keypress"?lo(t):t.type==="keydown"||t.type==="keyup"?t.keyCode:0}}),t_=Xe(e_),n_=le({},nl,{pointerId:0,width:0,height:0,pressure:0,tangentialPressure:0,tiltX:0,tiltY:0,twist:0,pointerType:0,isPrimary:0}),sf=Xe(n_),r_=le({},vs,{touches:0,targetTouches:0,changedTouches:0,altKey:0,metaKey:0,ctrlKey:0,shiftKey:0,getModifierState:Ju}),i_=Xe(r_),s_=le({},Jr,{propertyName:0,elapsedTime:0,pseudoElement:0}),o_=Xe(s_),l_=le({},nl,{deltaX:function(t){return"deltaX"in t?t.deltaX:"wheelDeltaX"in t?-t.wheelDeltaX:0},deltaY:function(t){return"deltaY"in t?t.deltaY:"wheelDeltaY"in t?-t.wheelDeltaY:"wheelDelta"in t?-t.wheelDelta:0},deltaZ:0,deltaMode:0}),a_=Xe(l_),u_=[9,13,27,32],Qu=$t&&"CompositionEvent"in window,Ui=null;$t&&"documentMode"in document&&(Ui=document.documentMode);var c_=$t&&"TextEvent"in window&&!Ui,zp=$t&&(!Qu||Ui&&8<Ui&&11>=Ui),of=" ",lf=!1;function $p(t,e){switch(t){case"keyup":return u_.indexOf(e.keyCode)!==-1;case"keydown":return e.keyCode!==229;case"keypress":case"mousedown":case"focusout":return!0;default:return!1}}function bp(t){return t=t.detail,typeof t=="object"&&"data"in t?t.data:null}var vr=!1;function h_(t,e){switch(t){case"compositionend":return bp(e);case"keypress":return e.which!==32?null:(lf=!0,of);case"textInput":return t=e.data,t===of&&lf?null:t;default:return null}}function f_(t,e){if(vr)return t==="compositionend"||!Qu&&$p(t,e)?(t=Vp(),oo=qu=pn=null,vr=!1,t):null;switch(t){case"paste":return null;case"keypress":if(!(e.ctrlKey||e.altKey||e.metaKey)||e.ctrlKey&&e.altKey){if(e.char&&1<e.char.length)return e.char;if(e.which)return String.fromCharCode(e.which)}return null;case"compositionend":return zp&&e.locale!=="ko"?null:e.data;default:return null}}var d_={color:!0,date:!0,datetime:!0,"datetime-local":!0,email:!0,month:!0,number:!0,password:!0,range:!0,search:!0,tel:!0,text:!0,time:!0,url:!0,week:!0};function af(t){var e=t&&t.nodeName&&t.nodeName.toLowerCase();return e==="input"?!!d_[t.type]:e==="textarea"}function Bp(t,e,n,r){wp(r),e=Ao(e,"onChange"),0<e.length&&(n=new Xu("onChange","change",null,n,r),t.push({event:n,listeners:e}))}var Fi=null,ts=null;function p_(t){eg(t,0)}function rl(t){var e=Er(t);if(dp(e))return t}function g_(t,e){if(t==="change")return e}var Hp=!1;if($t){var ea;if($t){var ta="oninput"in document;if(!ta){var uf=document.createElement("div");uf.setAttribute("oninput","return;"),ta=typeof uf.oninput=="function"}ea=ta}else ea=!1;Hp=ea&&(!document.documentMode||9<document.documentMode)}function cf(){Fi&&(Fi.detachEvent("onpropertychange",Wp),ts=Fi=null)}function Wp(t){if(t.propertyName==="value"&&rl(ts)){var e=[];Bp(e,ts,t,Bu(t)),Tp(p_,e)}}function m_(t,e,n){t==="focusin"?(cf(),Fi=e,ts=n,Fi.attachEvent("onpropertychange",Wp)):t==="focusout"&&cf()}function y_(t){if(t==="selectionchange"||t==="keyup"||t==="keydown")return rl(ts)}function v_(t,e){if(t==="click")return rl(e)}function __(t,e){if(t==="input"||t==="change")return rl(e)}function w_(t,e){return t===e&&(t!==0||1/t===1/e)||t!==t&&e!==e}var pt=typeof Object.is=="function"?Object.is:w_;function ns(t,e){if(pt(t,e))return!0;if(typeof t!="object"||t===null||typeof e!="object"||e===null)return!1;var n=Object.keys(t),r=Object.keys(e);if(n.length!==r.length)return!1;for(r=0;r<n.length;r++){var i=n[r];if(!Na.call(e,i)||!pt(t[i],e[i]))return!1}return!0}function hf(t){for(;t&&t.firstChild;)t=t.firstChild;return t}function ff(t,e){var n=hf(t);t=0;for(var r;n;){if(n.nodeType===3){if(r=t+n.textContent.length,t<=e&&r>=e)return{node:n,offset:e-t};t=r}e:{for(;n;){if(n.nextSibling){n=n.nextSibling;break e}n=n.parentNode}n=void 0}n=hf(n)}}function Gp(t,e){return t&&e?t===e?!0:t&&t.nodeType===3?!1:e&&e.nodeType===3?Gp(t,e.parentNode):"contains"in t?t.contains(e):t.compareDocumentPosition?!!(t.compareDocumentPosition(e)&16):!1:!1}function Kp(){for(var t=window,e=Eo();e instanceof t.HTMLIFrameElement;){try{var n=typeof e.contentWindow.location.href=="string"}catch{n=!1}if(n)t=e.contentWindow;else break;e=Eo(t.document)}return e}function Yu(t){var e=t&&t.nodeName&&t.nodeName.toLowerCase();return e&&(e==="input"&&(t.type==="text"||t.type==="search"||t.type==="tel"||t.type==="url"||t.type==="password")||e==="textarea"||t.contentEditable==="true")}function E_(t){var e=Kp(),n=t.focusedElem,r=t.selectionRange;if(e!==n&&n&&n.ownerDocument&&Gp(n.ownerDocument.documentElement,n)){if(r!==null&&Yu(n)){if(e=r.start,t=r.end,t===void 0&&(t=e),"selectionStart"in n)n.selectionStart=e,n.selectionEnd=Math.min(t,n.value.length);else if(t=(e=n.ownerDocument||document)&&e.defaultView||window,t.getSelection){t=t.getSelection();var i=n.textContent.length,o=Math.min(r.start,i);r=r.end===void 0?o:Math.min(r.end,i),!t.extend&&o>r&&(i=r,r=o,o=i),i=ff(n,o);var l=ff(n,r);i&&l&&(t.rangeCount!==1||t.anchorNode!==i.node||t.anchorOffset!==i.offset||t.focusNode!==l.node||t.focusOffset!==l.offset)&&(e=e.createRange(),e.setStart(i.node,i.offset),t.removeAllRanges(),o>r?(t.addRange(e),t.extend(l.node,l.offset)):(e.setEnd(l.node,l.offset),t.addRange(e)))}}for(e=[],t=n;t=t.parentNode;)t.nodeType===1&&e.push({element:t,left:t.scrollLeft,top:t.scrollTop});for(typeof n.focus=="function"&&n.focus(),n=0;n<e.length;n++)t=e[n],t.element.scrollLeft=t.left,t.element.scrollTop=t.top}}var S_=$t&&"documentMode"in document&&11>=document.documentMode,_r=null,Xa=null,ji=null,Ja=!1;function df(t,e,n){var r=n.window===n?n.document:n.nodeType===9?n:n.ownerDocument;Ja||_r==null||_r!==Eo(r)||(r=_r,"selectionStart"in r&&Yu(r)?r={start:r.selectionStart,end:r.selectionEnd}:(r=(r.ownerDocument&&r.ownerDocument.defaultView||window).getSelection(),r={anchorNode:r.anchorNode,anchorOffset:r.anchorOffset,focusNode:r.focusNode,focusOffset:r.focusOffset}),ji&&ns(ji,r)||(ji=r,r=Ao(Xa,"onSelect"),0<r.length&&(e=new Xu("onSelect","select",null,e,n),t.push({event:e,listeners:r}),e.target=_r)))}function Ws(t,e){var n={};return n[t.toLowerCase()]=e.toLowerCase(),n["Webkit"+t]="webkit"+e,n["Moz"+t]="moz"+e,n}var wr={animationend:Ws("Animation","AnimationEnd"),animationiteration:Ws("Animation","AnimationIteration"),animationstart:Ws("Animation","AnimationStart"),transitionend:Ws("Transition","TransitionEnd")},na={},qp={};$t&&(qp=document.createElement("div").style,"AnimationEvent"in window||(delete wr.animationend.animation,delete wr.animationiteration.animation,delete wr.animationstart.animation),"TransitionEvent"in window||delete wr.transitionend.transition);function il(t){if(na[t])return na[t];if(!wr[t])return t;var e=wr[t],n;for(n in e)if(e.hasOwnProperty(n)&&n in qp)return na[t]=e[n];return t}var Xp=il("animationend"),Jp=il("animationiteration"),Qp=il("animationstart"),Yp=il("transitionend"),Zp=new Map,pf="abort auxClick cancel canPlay canPlayThrough click close contextMenu copy cut drag dragEnd dragEnter dragExit dragLeave dragOver dragStart drop durationChange emptied encrypted ended error gotPointerCapture input invalid keyDown keyPress keyUp load loadedData loadedMetadata loadStart lostPointerCapture mouseDown mouseMove mouseOut mouseOver mouseUp paste pause play playing pointerCancel pointerDown pointerMove pointerOut pointerOver pointerUp progress rateChange reset resize seeked seeking stalled submit suspend timeUpdate touchCancel touchEnd touchStart volumeChange scroll toggle touchMove waiting wheel".split(" ");function Nn(t,e){Zp.set(t,e),ar(e,[t])}for(var ra=0;ra<pf.length;ra++){var ia=pf[ra],I_=ia.toLowerCase(),T_=ia[0].toUpperCase()+ia.slice(1);Nn(I_,"on"+T_)}Nn(Xp,"onAnimationEnd");Nn(Jp,"onAnimationIteration");Nn(Qp,"onAnimationStart");Nn("dblclick","onDoubleClick");Nn("focusin","onFocus");Nn("focusout","onBlur");Nn(Yp,"onTransitionEnd");Vr("onMouseEnter",["mouseout","mouseover"]);Vr("onMouseLeave",["mouseout","mouseover"]);Vr("onPointerEnter",["pointerout","pointerover"]);Vr("onPointerLeave",["pointerout","pointerover"]);ar("onChange","change click focusin focusout input keydown keyup selectionchange".split(" "));ar("onSelect","focusout contextmenu dragend focusin keydown keyup mousedown mouseup selectionchange".split(" "));ar("onBeforeInput",["compositionend","keypress","textInput","paste"]);ar("onCompositionEnd","compositionend focusout keydown keypress keyup mousedown".split(" "));ar("onCompositionStart","compositionstart focusout keydown keypress keyup mousedown".split(" "));ar("onCompositionUpdate","compositionupdate focusout keydown keypress keyup mousedown".split(" "));var Oi="abort canplay canplaythrough durationchange emptied encrypted ended error loadeddata loadedmetadata loadstart pause play playing progress ratechange resize seeked seeking stalled suspend timeupdate volumechange waiting".split(" "),k_=new Set("cancel close invalid load scroll toggle".split(" ").concat(Oi));function gf(t,e,n){var r=t.type||"unknown-event";t.currentTarget=n,Iv(r,e,void 0,t),t.currentTarget=null}function eg(t,e){e=(e&4)!==0;for(var n=0;n<t.length;n++){var r=t[n],i=r.event;r=r.listeners;e:{var o=void 0;if(e)for(var l=r.length-1;0<=l;l--){var u=r[l],h=u.instance,d=u.currentTarget;if(u=u.listener,h!==o&&i.isPropagationStopped())break e;gf(i,u,d),o=h}else for(l=0;l<r.length;l++){if(u=r[l],h=u.instance,d=u.currentTarget,u=u.listener,h!==o&&i.isPropagationStopped())break e;gf(i,u,d),o=h}}}if(Io)throw t=Wa,Io=!1,Wa=null,t}function te(t,e){var n=e[tu];n===void 0&&(n=e[tu]=new Set);var r=t+"__bubble";n.has(r)||(tg(e,t,2,!1),n.add(r))}function sa(t,e,n){var r=0;e&&(r|=4),tg(n,t,r,e)}var Gs="_reactListening"+Math.random().toString(36).slice(2);function rs(t){if(!t[Gs]){t[Gs]=!0,ap.forEach(function(n){n!=="selectionchange"&&(k_.has(n)||sa(n,!1,t),sa(n,!0,t))});var e=t.nodeType===9?t:t.ownerDocument;e===null||e[Gs]||(e[Gs]=!0,sa("selectionchange",!1,e))}}function tg(t,e,n,r){switch(jp(e)){case 1:var i=Vv;break;case 4:i=zv;break;default:i=Ku}n=i.bind(null,e,n,t),i=void 0,!Ha||e!=="touchstart"&&e!=="touchmove"&&e!=="wheel"||(i=!0),r?i!==void 0?t.addEventListener(e,n,{capture:!0,passive:i}):t.addEventListener(e,n,!0):i!==void 0?t.addEventListener(e,n,{passive:i}):t.addEventListener(e,n,!1)}function oa(t,e,n,r,i){var o=r;if(!(e&1)&&!(e&2)&&r!==null)e:for(;;){if(r===null)return;var l=r.tag;if(l===3||l===4){var u=r.stateNode.containerInfo;if(u===i||u.nodeType===8&&u.parentNode===i)break;if(l===4)for(l=r.return;l!==null;){var h=l.tag;if((h===3||h===4)&&(h=l.stateNode.containerInfo,h===i||h.nodeType===8&&h.parentNode===i))return;l=l.return}for(;u!==null;){if(l=Wn(u),l===null)return;if(h=l.tag,h===5||h===6){r=o=l;continue e}u=u.parentNode}}r=r.return}Tp(function(){var d=o,k=Bu(n),S=[];e:{var E=Zp.get(t);if(E!==void 0){var N=Xu,O=t;switch(t){case"keypress":if(lo(n)===0)break e;case"keydown":case"keyup":N=t_;break;case"focusin":O="focus",N=Zl;break;case"focusout":O="blur",N=Zl;break;case"beforeblur":case"afterblur":N=Zl;break;case"click":if(n.button===2)break e;case"auxclick":case"dblclick":case"mousedown":case"mousemove":case"mouseup":case"mouseout":case"mouseover":case"contextmenu":N=nf;break;case"drag":case"dragend":case"dragenter":case"dragexit":case"dragleave":case"dragover":case"dragstart":case"drop":N=Bv;break;case"touchcancel":case"touchend":case"touchmove":case"touchstart":N=i_;break;case Xp:case Jp:case Qp:N=Gv;break;case Yp:N=o_;break;case"scroll":N=$v;break;case"wheel":N=a_;break;case"copy":case"cut":case"paste":N=qv;break;case"gotpointercapture":case"lostpointercapture":case"pointercancel":case"pointerdown":case"pointermove":case"pointerout":case"pointerover":case"pointerup":N=sf}var L=(e&4)!==0,z=!L&&t==="scroll",I=L?E!==null?E+"Capture":null:E;L=[];for(var _=d,T;_!==null;){T=_;var R=T.stateNode;if(T.tag===5&&R!==null&&(T=R,I!==null&&(R=Qi(_,I),R!=null&&L.push(is(_,R,T)))),z)break;_=_.return}0<L.length&&(E=new N(E,O,null,n,k),S.push({event:E,listeners:L}))}}if(!(e&7)){e:{if(E=t==="mouseover"||t==="pointerover",N=t==="mouseout"||t==="pointerout",E&&n!==ba&&(O=n.relatedTarget||n.fromElement)&&(Wn(O)||O[bt]))break e;if((N||E)&&(E=k.window===k?k:(E=k.ownerDocument)?E.defaultView||E.parentWindow:window,N?(O=n.relatedTarget||n.toElement,N=d,O=O?Wn(O):null,O!==null&&(z=ur(O),O!==z||O.tag!==5&&O.tag!==6)&&(O=null)):(N=null,O=d),N!==O)){if(L=nf,R="onMouseLeave",I="onMouseEnter",_="mouse",(t==="pointerout"||t==="pointerover")&&(L=sf,R="onPointerLeave",I="onPointerEnter",_="pointer"),z=N==null?E:Er(N),T=O==null?E:Er(O),E=new L(R,_+"leave",N,n,k),E.target=z,E.relatedTarget=T,R=null,Wn(k)===d&&(L=new L(I,_+"enter",O,n,k),L.target=T,L.relatedTarget=z,R=L),z=R,N&&O)t:{for(L=N,I=O,_=0,T=L;T;T=gr(T))_++;for(T=0,R=I;R;R=gr(R))T++;for(;0<_-T;)L=gr(L),_--;for(;0<T-_;)I=gr(I),T--;for(;_--;){if(L===I||I!==null&&L===I.alternate)break t;L=gr(L),I=gr(I)}L=null}else L=null;N!==null&&mf(S,E,N,L,!1),O!==null&&z!==null&&mf(S,z,O,L,!0)}}e:{if(E=d?Er(d):window,N=E.nodeName&&E.nodeName.toLowerCase(),N==="select"||N==="input"&&E.type==="file")var M=g_;else if(af(E))if(Hp)M=__;else{M=y_;var U=m_}else(N=E.nodeName)&&N.toLowerCase()==="input"&&(E.type==="checkbox"||E.type==="radio")&&(M=v_);if(M&&(M=M(t,d))){Bp(S,M,n,k);break e}U&&U(t,E,d),t==="focusout"&&(U=E._wrapperState)&&U.controlled&&E.type==="number"&&Fa(E,"number",E.value)}switch(U=d?Er(d):window,t){case"focusin":(af(U)||U.contentEditable==="true")&&(_r=U,Xa=d,ji=null);break;case"focusout":ji=Xa=_r=null;break;case"mousedown":Ja=!0;break;case"contextmenu":case"mouseup":case"dragend":Ja=!1,df(S,n,k);break;case"selectionchange":if(S_)break;case"keydown":case"keyup":df(S,n,k)}var g;if(Qu)e:{switch(t){case"compositionstart":var p="onCompositionStart";break e;case"compositionend":p="onCompositionEnd";break e;case"compositionupdate":p="onCompositionUpdate";break e}p=void 0}else vr?$p(t,n)&&(p="onCompositionEnd"):t==="keydown"&&n.keyCode===229&&(p="onCompositionStart");p&&(zp&&n.locale!=="ko"&&(vr||p!=="onCompositionStart"?p==="onCompositionEnd"&&vr&&(g=Vp()):(pn=k,qu="value"in pn?pn.value:pn.textContent,vr=!0)),U=Ao(d,p),0<U.length&&(p=new rf(p,t,null,n,k),S.push({event:p,listeners:U}),g?p.data=g:(g=bp(n),g!==null&&(p.data=g)))),(g=c_?h_(t,n):f_(t,n))&&(d=Ao(d,"onBeforeInput"),0<d.length&&(k=new rf("onBeforeInput","beforeinput",null,n,k),S.push({event:k,listeners:d}),k.data=g))}eg(S,e)})}function is(t,e,n){return{instance:t,listener:e,currentTarget:n}}function Ao(t,e){for(var n=e+"Capture",r=[];t!==null;){var i=t,o=i.stateNode;i.tag===5&&o!==null&&(i=o,o=Qi(t,n),o!=null&&r.unshift(is(t,o,i)),o=Qi(t,e),o!=null&&r.push(is(t,o,i))),t=t.return}return r}function gr(t){if(t===null)return null;do t=t.return;while(t&&t.tag!==5);return t||null}function mf(t,e,n,r,i){for(var o=e._reactName,l=[];n!==null&&n!==r;){var u=n,h=u.alternate,d=u.stateNode;if(h!==null&&h===r)break;u.tag===5&&d!==null&&(u=d,i?(h=Qi(n,o),h!=null&&l.unshift(is(n,h,u))):i||(h=Qi(n,o),h!=null&&l.push(is(n,h,u)))),n=n.return}l.length!==0&&t.push({event:e,listeners:l})}var C_=/\r\n?/g,P_=/\u0000|\uFFFD/g;function yf(t){return(typeof t=="string"?t:""+t).replace(C_,`
`).replace(P_,"")}function Ks(t,e,n){if(e=yf(e),yf(t)!==e&&n)throw Error(D(425))}function Ro(){}var Qa=null,Ya=null;function Za(t,e){return t==="textarea"||t==="noscript"||typeof e.children=="string"||typeof e.children=="number"||typeof e.dangerouslySetInnerHTML=="object"&&e.dangerouslySetInnerHTML!==null&&e.dangerouslySetInnerHTML.__html!=null}var eu=typeof setTimeout=="function"?setTimeout:void 0,A_=typeof clearTimeout=="function"?clearTimeout:void 0,vf=typeof Promise=="function"?Promise:void 0,R_=typeof queueMicrotask=="function"?queueMicrotask:typeof vf<"u"?function(t){return vf.resolve(null).then(t).catch(N_)}:eu;function N_(t){setTimeout(function(){throw t})}function la(t,e){var n=e,r=0;do{var i=n.nextSibling;if(t.removeChild(n),i&&i.nodeType===8)if(n=i.data,n==="/$"){if(r===0){t.removeChild(i),es(e);return}r--}else n!=="$"&&n!=="$?"&&n!=="$!"||r++;n=i}while(n);es(e)}function _n(t){for(;t!=null;t=t.nextSibling){var e=t.nodeType;if(e===1||e===3)break;if(e===8){if(e=t.data,e==="$"||e==="$!"||e==="$?")break;if(e==="/$")return null}}return t}function _f(t){t=t.previousSibling;for(var e=0;t;){if(t.nodeType===8){var n=t.data;if(n==="$"||n==="$!"||n==="$?"){if(e===0)return t;e--}else n==="/$"&&e++}t=t.previousSibling}return null}var Qr=Math.random().toString(36).slice(2),St="__reactFiber$"+Qr,ss="__reactProps$"+Qr,bt="__reactContainer$"+Qr,tu="__reactEvents$"+Qr,O_="__reactListeners$"+Qr,D_="__reactHandles$"+Qr;function Wn(t){var e=t[St];if(e)return e;for(var n=t.parentNode;n;){if(e=n[bt]||n[St]){if(n=e.alternate,e.child!==null||n!==null&&n.child!==null)for(t=_f(t);t!==null;){if(n=t[St])return n;t=_f(t)}return e}t=n,n=t.parentNode}return null}function _s(t){return t=t[St]||t[bt],!t||t.tag!==5&&t.tag!==6&&t.tag!==13&&t.tag!==3?null:t}function Er(t){if(t.tag===5||t.tag===6)return t.stateNode;throw Error(D(33))}function sl(t){return t[ss]||null}var nu=[],Sr=-1;function On(t){return{current:t}}function ne(t){0>Sr||(t.current=nu[Sr],nu[Sr]=null,Sr--)}function Z(t,e){Sr++,nu[Sr]=t.current,t.current=e}var An={},Re=On(An),ze=On(!1),er=An;function zr(t,e){var n=t.type.contextTypes;if(!n)return An;var r=t.stateNode;if(r&&r.__reactInternalMemoizedUnmaskedChildContext===e)return r.__reactInternalMemoizedMaskedChildContext;var i={},o;for(o in n)i[o]=e[o];return r&&(t=t.stateNode,t.__reactInternalMemoizedUnmaskedChildContext=e,t.__reactInternalMemoizedMaskedChildContext=i),i}function $e(t){return t=t.childContextTypes,t!=null}function No(){ne(ze),ne(Re)}function wf(t,e,n){if(Re.current!==An)throw Error(D(168));Z(Re,e),Z(ze,n)}function ng(t,e,n){var r=t.stateNode;if(e=e.childContextTypes,typeof r.getChildContext!="function")return n;r=r.getChildContext();for(var i in r)if(!(i in e))throw Error(D(108,mv(t)||"Unknown",i));return le({},n,r)}function Oo(t){return t=(t=t.stateNode)&&t.__reactInternalMemoizedMergedChildContext||An,er=Re.current,Z(Re,t),Z(ze,ze.current),!0}function Ef(t,e,n){var r=t.stateNode;if(!r)throw Error(D(169));n?(t=ng(t,e,er),r.__reactInternalMemoizedMergedChildContext=t,ne(ze),ne(Re),Z(Re,t)):ne(ze),Z(ze,n)}var Dt=null,ol=!1,aa=!1;function rg(t){Dt===null?Dt=[t]:Dt.push(t)}function L_(t){ol=!0,rg(t)}function Dn(){if(!aa&&Dt!==null){aa=!0;var t=0,e=Q;try{var n=Dt;for(Q=1;t<n.length;t++){var r=n[t];do r=r(!0);while(r!==null)}Dt=null,ol=!1}catch(i){throw Dt!==null&&(Dt=Dt.slice(t+1)),Ap(Hu,Dn),i}finally{Q=e,aa=!1}}return null}var Ir=[],Tr=0,Do=null,Lo=0,Ye=[],Ze=0,tr=null,Ut=1,Ft="";function $n(t,e){Ir[Tr++]=Lo,Ir[Tr++]=Do,Do=t,Lo=e}function ig(t,e,n){Ye[Ze++]=Ut,Ye[Ze++]=Ft,Ye[Ze++]=tr,tr=t;var r=Ut;t=Ft;var i=32-ft(r)-1;r&=~(1<<i),n+=1;var o=32-ft(e)+i;if(30<o){var l=i-i%5;o=(r&(1<<l)-1).toString(32),r>>=l,i-=l,Ut=1<<32-ft(e)+i|n<<i|r,Ft=o+t}else Ut=1<<o|n<<i|r,Ft=t}function Zu(t){t.return!==null&&($n(t,1),ig(t,1,0))}function ec(t){for(;t===Do;)Do=Ir[--Tr],Ir[Tr]=null,Lo=Ir[--Tr],Ir[Tr]=null;for(;t===tr;)tr=Ye[--Ze],Ye[Ze]=null,Ft=Ye[--Ze],Ye[Ze]=null,Ut=Ye[--Ze],Ye[Ze]=null}var Ge=null,We=null,ie=!1,at=null;function sg(t,e){var n=et(5,null,null,0);n.elementType="DELETED",n.stateNode=e,n.return=t,e=t.deletions,e===null?(t.deletions=[n],t.flags|=16):e.push(n)}function Sf(t,e){switch(t.tag){case 5:var n=t.type;return e=e.nodeType!==1||n.toLowerCase()!==e.nodeName.toLowerCase()?null:e,e!==null?(t.stateNode=e,Ge=t,We=_n(e.firstChild),!0):!1;case 6:return e=t.pendingProps===""||e.nodeType!==3?null:e,e!==null?(t.stateNode=e,Ge=t,We=null,!0):!1;case 13:return e=e.nodeType!==8?null:e,e!==null?(n=tr!==null?{id:Ut,overflow:Ft}:null,t.memoizedState={dehydrated:e,treeContext:n,retryLane:1073741824},n=et(18,null,null,0),n.stateNode=e,n.return=t,t.child=n,Ge=t,We=null,!0):!1;default:return!1}}function ru(t){return(t.mode&1)!==0&&(t.flags&128)===0}function iu(t){if(ie){var e=We;if(e){var n=e;if(!Sf(t,e)){if(ru(t))throw Error(D(418));e=_n(n.nextSibling);var r=Ge;e&&Sf(t,e)?sg(r,n):(t.flags=t.flags&-4097|2,ie=!1,Ge=t)}}else{if(ru(t))throw Error(D(418));t.flags=t.flags&-4097|2,ie=!1,Ge=t}}}function If(t){for(t=t.return;t!==null&&t.tag!==5&&t.tag!==3&&t.tag!==13;)t=t.return;Ge=t}function qs(t){if(t!==Ge)return!1;if(!ie)return If(t),ie=!0,!1;var e;if((e=t.tag!==3)&&!(e=t.tag!==5)&&(e=t.type,e=e!=="head"&&e!=="body"&&!Za(t.type,t.memoizedProps)),e&&(e=We)){if(ru(t))throw og(),Error(D(418));for(;e;)sg(t,e),e=_n(e.nextSibling)}if(If(t),t.tag===13){if(t=t.memoizedState,t=t!==null?t.dehydrated:null,!t)throw Error(D(317));e:{for(t=t.nextSibling,e=0;t;){if(t.nodeType===8){var n=t.data;if(n==="/$"){if(e===0){We=_n(t.nextSibling);break e}e--}else n!=="$"&&n!=="$!"&&n!=="$?"||e++}t=t.nextSibling}We=null}}else We=Ge?_n(t.stateNode.nextSibling):null;return!0}function og(){for(var t=We;t;)t=_n(t.nextSibling)}function $r(){We=Ge=null,ie=!1}function tc(t){at===null?at=[t]:at.push(t)}var x_=Xt.ReactCurrentBatchConfig;function ki(t,e,n){if(t=n.ref,t!==null&&typeof t!="function"&&typeof t!="object"){if(n._owner){if(n=n._owner,n){if(n.tag!==1)throw Error(D(309));var r=n.stateNode}if(!r)throw Error(D(147,t));var i=r,o=""+t;return e!==null&&e.ref!==null&&typeof e.ref=="function"&&e.ref._stringRef===o?e.ref:(e=function(l){var u=i.refs;l===null?delete u[o]:u[o]=l},e._stringRef=o,e)}if(typeof t!="string")throw Error(D(284));if(!n._owner)throw Error(D(290,t))}return t}function Xs(t,e){throw t=Object.prototype.toString.call(e),Error(D(31,t==="[object Object]"?"object with keys {"+Object.keys(e).join(", ")+"}":t))}function Tf(t){var e=t._init;return e(t._payload)}function lg(t){function e(I,_){if(t){var T=I.deletions;T===null?(I.deletions=[_],I.flags|=16):T.push(_)}}function n(I,_){if(!t)return null;for(;_!==null;)e(I,_),_=_.sibling;return null}function r(I,_){for(I=new Map;_!==null;)_.key!==null?I.set(_.key,_):I.set(_.index,_),_=_.sibling;return I}function i(I,_){return I=In(I,_),I.index=0,I.sibling=null,I}function o(I,_,T){return I.index=T,t?(T=I.alternate,T!==null?(T=T.index,T<_?(I.flags|=2,_):T):(I.flags|=2,_)):(I.flags|=1048576,_)}function l(I){return t&&I.alternate===null&&(I.flags|=2),I}function u(I,_,T,R){return _===null||_.tag!==6?(_=ga(T,I.mode,R),_.return=I,_):(_=i(_,T),_.return=I,_)}function h(I,_,T,R){var M=T.type;return M===yr?k(I,_,T.props.children,R,T.key):_!==null&&(_.elementType===M||typeof M=="object"&&M!==null&&M.$$typeof===ln&&Tf(M)===_.type)?(R=i(_,T.props),R.ref=ki(I,_,T),R.return=I,R):(R=go(T.type,T.key,T.props,null,I.mode,R),R.ref=ki(I,_,T),R.return=I,R)}function d(I,_,T,R){return _===null||_.tag!==4||_.stateNode.containerInfo!==T.containerInfo||_.stateNode.implementation!==T.implementation?(_=ma(T,I.mode,R),_.return=I,_):(_=i(_,T.children||[]),_.return=I,_)}function k(I,_,T,R,M){return _===null||_.tag!==7?(_=Jn(T,I.mode,R,M),_.return=I,_):(_=i(_,T),_.return=I,_)}function S(I,_,T){if(typeof _=="string"&&_!==""||typeof _=="number")return _=ga(""+_,I.mode,T),_.return=I,_;if(typeof _=="object"&&_!==null){switch(_.$$typeof){case js:return T=go(_.type,_.key,_.props,null,I.mode,T),T.ref=ki(I,null,_),T.return=I,T;case mr:return _=ma(_,I.mode,T),_.return=I,_;case ln:var R=_._init;return S(I,R(_._payload),T)}if(Ri(_)||wi(_))return _=Jn(_,I.mode,T,null),_.return=I,_;Xs(I,_)}return null}function E(I,_,T,R){var M=_!==null?_.key:null;if(typeof T=="string"&&T!==""||typeof T=="number")return M!==null?null:u(I,_,""+T,R);if(typeof T=="object"&&T!==null){switch(T.$$typeof){case js:return T.key===M?h(I,_,T,R):null;case mr:return T.key===M?d(I,_,T,R):null;case ln:return M=T._init,E(I,_,M(T._payload),R)}if(Ri(T)||wi(T))return M!==null?null:k(I,_,T,R,null);Xs(I,T)}return null}function N(I,_,T,R,M){if(typeof R=="string"&&R!==""||typeof R=="number")return I=I.get(T)||null,u(_,I,""+R,M);if(typeof R=="object"&&R!==null){switch(R.$$typeof){case js:return I=I.get(R.key===null?T:R.key)||null,h(_,I,R,M);case mr:return I=I.get(R.key===null?T:R.key)||null,d(_,I,R,M);case ln:var U=R._init;return N(I,_,T,U(R._payload),M)}if(Ri(R)||wi(R))return I=I.get(T)||null,k(_,I,R,M,null);Xs(_,R)}return null}function O(I,_,T,R){for(var M=null,U=null,g=_,p=_=0,m=null;g!==null&&p<T.length;p++){g.index>p?(m=g,g=null):m=g.sibling;var v=E(I,g,T[p],R);if(v===null){g===null&&(g=m);break}t&&g&&v.alternate===null&&e(I,g),_=o(v,_,p),U===null?M=v:U.sibling=v,U=v,g=m}if(p===T.length)return n(I,g),ie&&$n(I,p),M;if(g===null){for(;p<T.length;p++)g=S(I,T[p],R),g!==null&&(_=o(g,_,p),U===null?M=g:U.sibling=g,U=g);return ie&&$n(I,p),M}for(g=r(I,g);p<T.length;p++)m=N(g,I,p,T[p],R),m!==null&&(t&&m.alternate!==null&&g.delete(m.key===null?p:m.key),_=o(m,_,p),U===null?M=m:U.sibling=m,U=m);return t&&g.forEach(function(w){return e(I,w)}),ie&&$n(I,p),M}function L(I,_,T,R){var M=wi(T);if(typeof M!="function")throw Error(D(150));if(T=M.call(T),T==null)throw Error(D(151));for(var U=M=null,g=_,p=_=0,m=null,v=T.next();g!==null&&!v.done;p++,v=T.next()){g.index>p?(m=g,g=null):m=g.sibling;var w=E(I,g,v.value,R);if(w===null){g===null&&(g=m);break}t&&g&&w.alternate===null&&e(I,g),_=o(w,_,p),U===null?M=w:U.sibling=w,U=w,g=m}if(v.done)return n(I,g),ie&&$n(I,p),M;if(g===null){for(;!v.done;p++,v=T.next())v=S(I,v.value,R),v!==null&&(_=o(v,_,p),U===null?M=v:U.sibling=v,U=v);return ie&&$n(I,p),M}for(g=r(I,g);!v.done;p++,v=T.next())v=N(g,I,p,v.value,R),v!==null&&(t&&v.alternate!==null&&g.delete(v.key===null?p:v.key),_=o(v,_,p),U===null?M=v:U.sibling=v,U=v);return t&&g.forEach(function(C){return e(I,C)}),ie&&$n(I,p),M}function z(I,_,T,R){if(typeof T=="object"&&T!==null&&T.type===yr&&T.key===null&&(T=T.props.children),typeof T=="object"&&T!==null){switch(T.$$typeof){case js:e:{for(var M=T.key,U=_;U!==null;){if(U.key===M){if(M=T.type,M===yr){if(U.tag===7){n(I,U.sibling),_=i(U,T.props.children),_.return=I,I=_;break e}}else if(U.elementType===M||typeof M=="object"&&M!==null&&M.$$typeof===ln&&Tf(M)===U.type){n(I,U.sibling),_=i(U,T.props),_.ref=ki(I,U,T),_.return=I,I=_;break e}n(I,U);break}else e(I,U);U=U.sibling}T.type===yr?(_=Jn(T.props.children,I.mode,R,T.key),_.return=I,I=_):(R=go(T.type,T.key,T.props,null,I.mode,R),R.ref=ki(I,_,T),R.return=I,I=R)}return l(I);case mr:e:{for(U=T.key;_!==null;){if(_.key===U)if(_.tag===4&&_.stateNode.containerInfo===T.containerInfo&&_.stateNode.implementation===T.implementation){n(I,_.sibling),_=i(_,T.children||[]),_.return=I,I=_;break e}else{n(I,_);break}else e(I,_);_=_.sibling}_=ma(T,I.mode,R),_.return=I,I=_}return l(I);case ln:return U=T._init,z(I,_,U(T._payload),R)}if(Ri(T))return O(I,_,T,R);if(wi(T))return L(I,_,T,R);Xs(I,T)}return typeof T=="string"&&T!==""||typeof T=="number"?(T=""+T,_!==null&&_.tag===6?(n(I,_.sibling),_=i(_,T),_.return=I,I=_):(n(I,_),_=ga(T,I.mode,R),_.return=I,I=_),l(I)):n(I,_)}return z}var br=lg(!0),ag=lg(!1),xo=On(null),Mo=null,kr=null,nc=null;function rc(){nc=kr=Mo=null}function ic(t){var e=xo.current;ne(xo),t._currentValue=e}function su(t,e,n){for(;t!==null;){var r=t.alternate;if((t.childLanes&e)!==e?(t.childLanes|=e,r!==null&&(r.childLanes|=e)):r!==null&&(r.childLanes&e)!==e&&(r.childLanes|=e),t===n)break;t=t.return}}function Lr(t,e){Mo=t,nc=kr=null,t=t.dependencies,t!==null&&t.firstContext!==null&&(t.lanes&e&&(Ve=!0),t.firstContext=null)}function nt(t){var e=t._currentValue;if(nc!==t)if(t={context:t,memoizedValue:e,next:null},kr===null){if(Mo===null)throw Error(D(308));kr=t,Mo.dependencies={lanes:0,firstContext:t}}else kr=kr.next=t;return e}var Gn=null;function sc(t){Gn===null?Gn=[t]:Gn.push(t)}function ug(t,e,n,r){var i=e.interleaved;return i===null?(n.next=n,sc(e)):(n.next=i.next,i.next=n),e.interleaved=n,Bt(t,r)}function Bt(t,e){t.lanes|=e;var n=t.alternate;for(n!==null&&(n.lanes|=e),n=t,t=t.return;t!==null;)t.childLanes|=e,n=t.alternate,n!==null&&(n.childLanes|=e),n=t,t=t.return;return n.tag===3?n.stateNode:null}var an=!1;function oc(t){t.updateQueue={baseState:t.memoizedState,firstBaseUpdate:null,lastBaseUpdate:null,shared:{pending:null,interleaved:null,lanes:0},effects:null}}function cg(t,e){t=t.updateQueue,e.updateQueue===t&&(e.updateQueue={baseState:t.baseState,firstBaseUpdate:t.firstBaseUpdate,lastBaseUpdate:t.lastBaseUpdate,shared:t.shared,effects:t.effects})}function zt(t,e){return{eventTime:t,lane:e,tag:0,payload:null,callback:null,next:null}}function wn(t,e,n){var r=t.updateQueue;if(r===null)return null;if(r=r.shared,q&2){var i=r.pending;return i===null?e.next=e:(e.next=i.next,i.next=e),r.pending=e,Bt(t,n)}return i=r.interleaved,i===null?(e.next=e,sc(r)):(e.next=i.next,i.next=e),r.interleaved=e,Bt(t,n)}function ao(t,e,n){if(e=e.updateQueue,e!==null&&(e=e.shared,(n&4194240)!==0)){var r=e.lanes;r&=t.pendingLanes,n|=r,e.lanes=n,Wu(t,n)}}function kf(t,e){var n=t.updateQueue,r=t.alternate;if(r!==null&&(r=r.updateQueue,n===r)){var i=null,o=null;if(n=n.firstBaseUpdate,n!==null){do{var l={eventTime:n.eventTime,lane:n.lane,tag:n.tag,payload:n.payload,callback:n.callback,next:null};o===null?i=o=l:o=o.next=l,n=n.next}while(n!==null);o===null?i=o=e:o=o.next=e}else i=o=e;n={baseState:r.baseState,firstBaseUpdate:i,lastBaseUpdate:o,shared:r.shared,effects:r.effects},t.updateQueue=n;return}t=n.lastBaseUpdate,t===null?n.firstBaseUpdate=e:t.next=e,n.lastBaseUpdate=e}function Uo(t,e,n,r){var i=t.updateQueue;an=!1;var o=i.firstBaseUpdate,l=i.lastBaseUpdate,u=i.shared.pending;if(u!==null){i.shared.pending=null;var h=u,d=h.next;h.next=null,l===null?o=d:l.next=d,l=h;var k=t.alternate;k!==null&&(k=k.updateQueue,u=k.lastBaseUpdate,u!==l&&(u===null?k.firstBaseUpdate=d:u.next=d,k.lastBaseUpdate=h))}if(o!==null){var S=i.baseState;l=0,k=d=h=null,u=o;do{var E=u.lane,N=u.eventTime;if((r&E)===E){k!==null&&(k=k.next={eventTime:N,lane:0,tag:u.tag,payload:u.payload,callback:u.callback,next:null});e:{var O=t,L=u;switch(E=e,N=n,L.tag){case 1:if(O=L.payload,typeof O=="function"){S=O.call(N,S,E);break e}S=O;break e;case 3:O.flags=O.flags&-65537|128;case 0:if(O=L.payload,E=typeof O=="function"?O.call(N,S,E):O,E==null)break e;S=le({},S,E);break e;case 2:an=!0}}u.callback!==null&&u.lane!==0&&(t.flags|=64,E=i.effects,E===null?i.effects=[u]:E.push(u))}else N={eventTime:N,lane:E,tag:u.tag,payload:u.payload,callback:u.callback,next:null},k===null?(d=k=N,h=S):k=k.next=N,l|=E;if(u=u.next,u===null){if(u=i.shared.pending,u===null)break;E=u,u=E.next,E.next=null,i.lastBaseUpdate=E,i.shared.pending=null}}while(!0);if(k===null&&(h=S),i.baseState=h,i.firstBaseUpdate=d,i.lastBaseUpdate=k,e=i.shared.interleaved,e!==null){i=e;do l|=i.lane,i=i.next;while(i!==e)}else o===null&&(i.shared.lanes=0);rr|=l,t.lanes=l,t.memoizedState=S}}function Cf(t,e,n){if(t=e.effects,e.effects=null,t!==null)for(e=0;e<t.length;e++){var r=t[e],i=r.callback;if(i!==null){if(r.callback=null,r=n,typeof i!="function")throw Error(D(191,i));i.call(r)}}}var ws={},Ct=On(ws),os=On(ws),ls=On(ws);function Kn(t){if(t===ws)throw Error(D(174));return t}function lc(t,e){switch(Z(ls,e),Z(os,t),Z(Ct,ws),t=e.nodeType,t){case 9:case 11:e=(e=e.documentElement)?e.namespaceURI:Va(null,"");break;default:t=t===8?e.parentNode:e,e=t.namespaceURI||null,t=t.tagName,e=Va(e,t)}ne(Ct),Z(Ct,e)}function Br(){ne(Ct),ne(os),ne(ls)}function hg(t){Kn(ls.current);var e=Kn(Ct.current),n=Va(e,t.type);e!==n&&(Z(os,t),Z(Ct,n))}function ac(t){os.current===t&&(ne(Ct),ne(os))}var se=On(0);function Fo(t){for(var e=t;e!==null;){if(e.tag===13){var n=e.memoizedState;if(n!==null&&(n=n.dehydrated,n===null||n.data==="$?"||n.data==="$!"))return e}else if(e.tag===19&&e.memoizedProps.revealOrder!==void 0){if(e.flags&128)return e}else if(e.child!==null){e.child.return=e,e=e.child;continue}if(e===t)break;for(;e.sibling===null;){if(e.return===null||e.return===t)return null;e=e.return}e.sibling.return=e.return,e=e.sibling}return null}var ua=[];function uc(){for(var t=0;t<ua.length;t++)ua[t]._workInProgressVersionPrimary=null;ua.length=0}var uo=Xt.ReactCurrentDispatcher,ca=Xt.ReactCurrentBatchConfig,nr=0,oe=null,ge=null,ve=null,jo=!1,Vi=!1,as=0,M_=0;function ke(){throw Error(D(321))}function cc(t,e){if(e===null)return!1;for(var n=0;n<e.length&&n<t.length;n++)if(!pt(t[n],e[n]))return!1;return!0}function hc(t,e,n,r,i,o){if(nr=o,oe=e,e.memoizedState=null,e.updateQueue=null,e.lanes=0,uo.current=t===null||t.memoizedState===null?V_:z_,t=n(r,i),Vi){o=0;do{if(Vi=!1,as=0,25<=o)throw Error(D(301));o+=1,ve=ge=null,e.updateQueue=null,uo.current=$_,t=n(r,i)}while(Vi)}if(uo.current=Vo,e=ge!==null&&ge.next!==null,nr=0,ve=ge=oe=null,jo=!1,e)throw Error(D(300));return t}function fc(){var t=as!==0;return as=0,t}function _t(){var t={memoizedState:null,baseState:null,baseQueue:null,queue:null,next:null};return ve===null?oe.memoizedState=ve=t:ve=ve.next=t,ve}function rt(){if(ge===null){var t=oe.alternate;t=t!==null?t.memoizedState:null}else t=ge.next;var e=ve===null?oe.memoizedState:ve.next;if(e!==null)ve=e,ge=t;else{if(t===null)throw Error(D(310));ge=t,t={memoizedState:ge.memoizedState,baseState:ge.baseState,baseQueue:ge.baseQueue,queue:ge.queue,next:null},ve===null?oe.memoizedState=ve=t:ve=ve.next=t}return ve}function us(t,e){return typeof e=="function"?e(t):e}function ha(t){var e=rt(),n=e.queue;if(n===null)throw Error(D(311));n.lastRenderedReducer=t;var r=ge,i=r.baseQueue,o=n.pending;if(o!==null){if(i!==null){var l=i.next;i.next=o.next,o.next=l}r.baseQueue=i=o,n.pending=null}if(i!==null){o=i.next,r=r.baseState;var u=l=null,h=null,d=o;do{var k=d.lane;if((nr&k)===k)h!==null&&(h=h.next={lane:0,action:d.action,hasEagerState:d.hasEagerState,eagerState:d.eagerState,next:null}),r=d.hasEagerState?d.eagerState:t(r,d.action);else{var S={lane:k,action:d.action,hasEagerState:d.hasEagerState,eagerState:d.eagerState,next:null};h===null?(u=h=S,l=r):h=h.next=S,oe.lanes|=k,rr|=k}d=d.next}while(d!==null&&d!==o);h===null?l=r:h.next=u,pt(r,e.memoizedState)||(Ve=!0),e.memoizedState=r,e.baseState=l,e.baseQueue=h,n.lastRenderedState=r}if(t=n.interleaved,t!==null){i=t;do o=i.lane,oe.lanes|=o,rr|=o,i=i.next;while(i!==t)}else i===null&&(n.lanes=0);return[e.memoizedState,n.dispatch]}function fa(t){var e=rt(),n=e.queue;if(n===null)throw Error(D(311));n.lastRenderedReducer=t;var r=n.dispatch,i=n.pending,o=e.memoizedState;if(i!==null){n.pending=null;var l=i=i.next;do o=t(o,l.action),l=l.next;while(l!==i);pt(o,e.memoizedState)||(Ve=!0),e.memoizedState=o,e.baseQueue===null&&(e.baseState=o),n.lastRenderedState=o}return[o,r]}function fg(){}function dg(t,e){var n=oe,r=rt(),i=e(),o=!pt(r.memoizedState,i);if(o&&(r.memoizedState=i,Ve=!0),r=r.queue,dc(mg.bind(null,n,r,t),[t]),r.getSnapshot!==e||o||ve!==null&&ve.memoizedState.tag&1){if(n.flags|=2048,cs(9,gg.bind(null,n,r,i,e),void 0,null),_e===null)throw Error(D(349));nr&30||pg(n,e,i)}return i}function pg(t,e,n){t.flags|=16384,t={getSnapshot:e,value:n},e=oe.updateQueue,e===null?(e={lastEffect:null,stores:null},oe.updateQueue=e,e.stores=[t]):(n=e.stores,n===null?e.stores=[t]:n.push(t))}function gg(t,e,n,r){e.value=n,e.getSnapshot=r,yg(e)&&vg(t)}function mg(t,e,n){return n(function(){yg(e)&&vg(t)})}function yg(t){var e=t.getSnapshot;t=t.value;try{var n=e();return!pt(t,n)}catch{return!0}}function vg(t){var e=Bt(t,1);e!==null&&dt(e,t,1,-1)}function Pf(t){var e=_t();return typeof t=="function"&&(t=t()),e.memoizedState=e.baseState=t,t={pending:null,interleaved:null,lanes:0,dispatch:null,lastRenderedReducer:us,lastRenderedState:t},e.queue=t,t=t.dispatch=j_.bind(null,oe,t),[e.memoizedState,t]}function cs(t,e,n,r){return t={tag:t,create:e,destroy:n,deps:r,next:null},e=oe.updateQueue,e===null?(e={lastEffect:null,stores:null},oe.updateQueue=e,e.lastEffect=t.next=t):(n=e.lastEffect,n===null?e.lastEffect=t.next=t:(r=n.next,n.next=t,t.next=r,e.lastEffect=t)),t}function _g(){return rt().memoizedState}function co(t,e,n,r){var i=_t();oe.flags|=t,i.memoizedState=cs(1|e,n,void 0,r===void 0?null:r)}function ll(t,e,n,r){var i=rt();r=r===void 0?null:r;var o=void 0;if(ge!==null){var l=ge.memoizedState;if(o=l.destroy,r!==null&&cc(r,l.deps)){i.memoizedState=cs(e,n,o,r);return}}oe.flags|=t,i.memoizedState=cs(1|e,n,o,r)}function Af(t,e){return co(8390656,8,t,e)}function dc(t,e){return ll(2048,8,t,e)}function wg(t,e){return ll(4,2,t,e)}function Eg(t,e){return ll(4,4,t,e)}function Sg(t,e){if(typeof e=="function")return t=t(),e(t),function(){e(null)};if(e!=null)return t=t(),e.current=t,function(){e.current=null}}function Ig(t,e,n){return n=n!=null?n.concat([t]):null,ll(4,4,Sg.bind(null,e,t),n)}function pc(){}function Tg(t,e){var n=rt();e=e===void 0?null:e;var r=n.memoizedState;return r!==null&&e!==null&&cc(e,r[1])?r[0]:(n.memoizedState=[t,e],t)}function kg(t,e){var n=rt();e=e===void 0?null:e;var r=n.memoizedState;return r!==null&&e!==null&&cc(e,r[1])?r[0]:(t=t(),n.memoizedState=[t,e],t)}function Cg(t,e,n){return nr&21?(pt(n,e)||(n=Op(),oe.lanes|=n,rr|=n,t.baseState=!0),e):(t.baseState&&(t.baseState=!1,Ve=!0),t.memoizedState=n)}function U_(t,e){var n=Q;Q=n!==0&&4>n?n:4,t(!0);var r=ca.transition;ca.transition={};try{t(!1),e()}finally{Q=n,ca.transition=r}}function Pg(){return rt().memoizedState}function F_(t,e,n){var r=Sn(t);if(n={lane:r,action:n,hasEagerState:!1,eagerState:null,next:null},Ag(t))Rg(e,n);else if(n=ug(t,e,n,r),n!==null){var i=xe();dt(n,t,r,i),Ng(n,e,r)}}function j_(t,e,n){var r=Sn(t),i={lane:r,action:n,hasEagerState:!1,eagerState:null,next:null};if(Ag(t))Rg(e,i);else{var o=t.alternate;if(t.lanes===0&&(o===null||o.lanes===0)&&(o=e.lastRenderedReducer,o!==null))try{var l=e.lastRenderedState,u=o(l,n);if(i.hasEagerState=!0,i.eagerState=u,pt(u,l)){var h=e.interleaved;h===null?(i.next=i,sc(e)):(i.next=h.next,h.next=i),e.interleaved=i;return}}catch{}finally{}n=ug(t,e,i,r),n!==null&&(i=xe(),dt(n,t,r,i),Ng(n,e,r))}}function Ag(t){var e=t.alternate;return t===oe||e!==null&&e===oe}function Rg(t,e){Vi=jo=!0;var n=t.pending;n===null?e.next=e:(e.next=n.next,n.next=e),t.pending=e}function Ng(t,e,n){if(n&4194240){var r=e.lanes;r&=t.pendingLanes,n|=r,e.lanes=n,Wu(t,n)}}var Vo={readContext:nt,useCallback:ke,useContext:ke,useEffect:ke,useImperativeHandle:ke,useInsertionEffect:ke,useLayoutEffect:ke,useMemo:ke,useReducer:ke,useRef:ke,useState:ke,useDebugValue:ke,useDeferredValue:ke,useTransition:ke,useMutableSource:ke,useSyncExternalStore:ke,useId:ke,unstable_isNewReconciler:!1},V_={readContext:nt,useCallback:function(t,e){return _t().memoizedState=[t,e===void 0?null:e],t},useContext:nt,useEffect:Af,useImperativeHandle:function(t,e,n){return n=n!=null?n.concat([t]):null,co(4194308,4,Sg.bind(null,e,t),n)},useLayoutEffect:function(t,e){return co(4194308,4,t,e)},useInsertionEffect:function(t,e){return co(4,2,t,e)},useMemo:function(t,e){var n=_t();return e=e===void 0?null:e,t=t(),n.memoizedState=[t,e],t},useReducer:function(t,e,n){var r=_t();return e=n!==void 0?n(e):e,r.memoizedState=r.baseState=e,t={pending:null,interleaved:null,lanes:0,dispatch:null,lastRenderedReducer:t,lastRenderedState:e},r.queue=t,t=t.dispatch=F_.bind(null,oe,t),[r.memoizedState,t]},useRef:function(t){var e=_t();return t={current:t},e.memoizedState=t},useState:Pf,useDebugValue:pc,useDeferredValue:function(t){return _t().memoizedState=t},useTransition:function(){var t=Pf(!1),e=t[0];return t=U_.bind(null,t[1]),_t().memoizedState=t,[e,t]},useMutableSource:function(){},useSyncExternalStore:function(t,e,n){var r=oe,i=_t();if(ie){if(n===void 0)throw Error(D(407));n=n()}else{if(n=e(),_e===null)throw Error(D(349));nr&30||pg(r,e,n)}i.memoizedState=n;var o={value:n,getSnapshot:e};return i.queue=o,Af(mg.bind(null,r,o,t),[t]),r.flags|=2048,cs(9,gg.bind(null,r,o,n,e),void 0,null),n},useId:function(){var t=_t(),e=_e.identifierPrefix;if(ie){var n=Ft,r=Ut;n=(r&~(1<<32-ft(r)-1)).toString(32)+n,e=":"+e+"R"+n,n=as++,0<n&&(e+="H"+n.toString(32)),e+=":"}else n=M_++,e=":"+e+"r"+n.toString(32)+":";return t.memoizedState=e},unstable_isNewReconciler:!1},z_={readContext:nt,useCallback:Tg,useContext:nt,useEffect:dc,useImperativeHandle:Ig,useInsertionEffect:wg,useLayoutEffect:Eg,useMemo:kg,useReducer:ha,useRef:_g,useState:function(){return ha(us)},useDebugValue:pc,useDeferredValue:function(t){var e=rt();return Cg(e,ge.memoizedState,t)},useTransition:function(){var t=ha(us)[0],e=rt().memoizedState;return[t,e]},useMutableSource:fg,useSyncExternalStore:dg,useId:Pg,unstable_isNewReconciler:!1},$_={readContext:nt,useCallback:Tg,useContext:nt,useEffect:dc,useImperativeHandle:Ig,useInsertionEffect:wg,useLayoutEffect:Eg,useMemo:kg,useReducer:fa,useRef:_g,useState:function(){return fa(us)},useDebugValue:pc,useDeferredValue:function(t){var e=rt();return ge===null?e.memoizedState=t:Cg(e,ge.memoizedState,t)},useTransition:function(){var t=fa(us)[0],e=rt().memoizedState;return[t,e]},useMutableSource:fg,useSyncExternalStore:dg,useId:Pg,unstable_isNewReconciler:!1};function ot(t,e){if(t&&t.defaultProps){e=le({},e),t=t.defaultProps;for(var n in t)e[n]===void 0&&(e[n]=t[n]);return e}return e}function ou(t,e,n,r){e=t.memoizedState,n=n(r,e),n=n==null?e:le({},e,n),t.memoizedState=n,t.lanes===0&&(t.updateQueue.baseState=n)}var al={isMounted:function(t){return(t=t._reactInternals)?ur(t)===t:!1},enqueueSetState:function(t,e,n){t=t._reactInternals;var r=xe(),i=Sn(t),o=zt(r,i);o.payload=e,n!=null&&(o.callback=n),e=wn(t,o,i),e!==null&&(dt(e,t,i,r),ao(e,t,i))},enqueueReplaceState:function(t,e,n){t=t._reactInternals;var r=xe(),i=Sn(t),o=zt(r,i);o.tag=1,o.payload=e,n!=null&&(o.callback=n),e=wn(t,o,i),e!==null&&(dt(e,t,i,r),ao(e,t,i))},enqueueForceUpdate:function(t,e){t=t._reactInternals;var n=xe(),r=Sn(t),i=zt(n,r);i.tag=2,e!=null&&(i.callback=e),e=wn(t,i,r),e!==null&&(dt(e,t,r,n),ao(e,t,r))}};function Rf(t,e,n,r,i,o,l){return t=t.stateNode,typeof t.shouldComponentUpdate=="function"?t.shouldComponentUpdate(r,o,l):e.prototype&&e.prototype.isPureReactComponent?!ns(n,r)||!ns(i,o):!0}function Og(t,e,n){var r=!1,i=An,o=e.contextType;return typeof o=="object"&&o!==null?o=nt(o):(i=$e(e)?er:Re.current,r=e.contextTypes,o=(r=r!=null)?zr(t,i):An),e=new e(n,o),t.memoizedState=e.state!==null&&e.state!==void 0?e.state:null,e.updater=al,t.stateNode=e,e._reactInternals=t,r&&(t=t.stateNode,t.__reactInternalMemoizedUnmaskedChildContext=i,t.__reactInternalMemoizedMaskedChildContext=o),e}function Nf(t,e,n,r){t=e.state,typeof e.componentWillReceiveProps=="function"&&e.componentWillReceiveProps(n,r),typeof e.UNSAFE_componentWillReceiveProps=="function"&&e.UNSAFE_componentWillReceiveProps(n,r),e.state!==t&&al.enqueueReplaceState(e,e.state,null)}function lu(t,e,n,r){var i=t.stateNode;i.props=n,i.state=t.memoizedState,i.refs={},oc(t);var o=e.contextType;typeof o=="object"&&o!==null?i.context=nt(o):(o=$e(e)?er:Re.current,i.context=zr(t,o)),i.state=t.memoizedState,o=e.getDerivedStateFromProps,typeof o=="function"&&(ou(t,e,o,n),i.state=t.memoizedState),typeof e.getDerivedStateFromProps=="function"||typeof i.getSnapshotBeforeUpdate=="function"||typeof i.UNSAFE_componentWillMount!="function"&&typeof i.componentWillMount!="function"||(e=i.state,typeof i.componentWillMount=="function"&&i.componentWillMount(),typeof i.UNSAFE_componentWillMount=="function"&&i.UNSAFE_componentWillMount(),e!==i.state&&al.enqueueReplaceState(i,i.state,null),Uo(t,n,i,r),i.state=t.memoizedState),typeof i.componentDidMount=="function"&&(t.flags|=4194308)}function Hr(t,e){try{var n="",r=e;do n+=gv(r),r=r.return;while(r);var i=n}catch(o){i=`
Error generating stack: `+o.message+`
`+o.stack}return{value:t,source:e,stack:i,digest:null}}function da(t,e,n){return{value:t,source:null,stack:n??null,digest:e??null}}function au(t,e){try{console.error(e.value)}catch(n){setTimeout(function(){throw n})}}var b_=typeof WeakMap=="function"?WeakMap:Map;function Dg(t,e,n){n=zt(-1,n),n.tag=3,n.payload={element:null};var r=e.value;return n.callback=function(){$o||($o=!0,vu=r),au(t,e)},n}function Lg(t,e,n){n=zt(-1,n),n.tag=3;var r=t.type.getDerivedStateFromError;if(typeof r=="function"){var i=e.value;n.payload=function(){return r(i)},n.callback=function(){au(t,e)}}var o=t.stateNode;return o!==null&&typeof o.componentDidCatch=="function"&&(n.callback=function(){au(t,e),typeof r!="function"&&(En===null?En=new Set([this]):En.add(this));var l=e.stack;this.componentDidCatch(e.value,{componentStack:l!==null?l:""})}),n}function Of(t,e,n){var r=t.pingCache;if(r===null){r=t.pingCache=new b_;var i=new Set;r.set(e,i)}else i=r.get(e),i===void 0&&(i=new Set,r.set(e,i));i.has(n)||(i.add(n),t=n0.bind(null,t,e,n),e.then(t,t))}function Df(t){do{var e;if((e=t.tag===13)&&(e=t.memoizedState,e=e!==null?e.dehydrated!==null:!0),e)return t;t=t.return}while(t!==null);return null}function Lf(t,e,n,r,i){return t.mode&1?(t.flags|=65536,t.lanes=i,t):(t===e?t.flags|=65536:(t.flags|=128,n.flags|=131072,n.flags&=-52805,n.tag===1&&(n.alternate===null?n.tag=17:(e=zt(-1,1),e.tag=2,wn(n,e,1))),n.lanes|=1),t)}var B_=Xt.ReactCurrentOwner,Ve=!1;function De(t,e,n,r){e.child=t===null?ag(e,null,n,r):br(e,t.child,n,r)}function xf(t,e,n,r,i){n=n.render;var o=e.ref;return Lr(e,i),r=hc(t,e,n,r,o,i),n=fc(),t!==null&&!Ve?(e.updateQueue=t.updateQueue,e.flags&=-2053,t.lanes&=~i,Ht(t,e,i)):(ie&&n&&Zu(e),e.flags|=1,De(t,e,r,i),e.child)}function Mf(t,e,n,r,i){if(t===null){var o=n.type;return typeof o=="function"&&!Sc(o)&&o.defaultProps===void 0&&n.compare===null&&n.defaultProps===void 0?(e.tag=15,e.type=o,xg(t,e,o,r,i)):(t=go(n.type,null,r,e,e.mode,i),t.ref=e.ref,t.return=e,e.child=t)}if(o=t.child,!(t.lanes&i)){var l=o.memoizedProps;if(n=n.compare,n=n!==null?n:ns,n(l,r)&&t.ref===e.ref)return Ht(t,e,i)}return e.flags|=1,t=In(o,r),t.ref=e.ref,t.return=e,e.child=t}function xg(t,e,n,r,i){if(t!==null){var o=t.memoizedProps;if(ns(o,r)&&t.ref===e.ref)if(Ve=!1,e.pendingProps=r=o,(t.lanes&i)!==0)t.flags&131072&&(Ve=!0);else return e.lanes=t.lanes,Ht(t,e,i)}return uu(t,e,n,r,i)}function Mg(t,e,n){var r=e.pendingProps,i=r.children,o=t!==null?t.memoizedState:null;if(r.mode==="hidden")if(!(e.mode&1))e.memoizedState={baseLanes:0,cachePool:null,transitions:null},Z(Pr,He),He|=n;else{if(!(n&1073741824))return t=o!==null?o.baseLanes|n:n,e.lanes=e.childLanes=1073741824,e.memoizedState={baseLanes:t,cachePool:null,transitions:null},e.updateQueue=null,Z(Pr,He),He|=t,null;e.memoizedState={baseLanes:0,cachePool:null,transitions:null},r=o!==null?o.baseLanes:n,Z(Pr,He),He|=r}else o!==null?(r=o.baseLanes|n,e.memoizedState=null):r=n,Z(Pr,He),He|=r;return De(t,e,i,n),e.child}function Ug(t,e){var n=e.ref;(t===null&&n!==null||t!==null&&t.ref!==n)&&(e.flags|=512,e.flags|=2097152)}function uu(t,e,n,r,i){var o=$e(n)?er:Re.current;return o=zr(e,o),Lr(e,i),n=hc(t,e,n,r,o,i),r=fc(),t!==null&&!Ve?(e.updateQueue=t.updateQueue,e.flags&=-2053,t.lanes&=~i,Ht(t,e,i)):(ie&&r&&Zu(e),e.flags|=1,De(t,e,n,i),e.child)}function Uf(t,e,n,r,i){if($e(n)){var o=!0;Oo(e)}else o=!1;if(Lr(e,i),e.stateNode===null)ho(t,e),Og(e,n,r),lu(e,n,r,i),r=!0;else if(t===null){var l=e.stateNode,u=e.memoizedProps;l.props=u;var h=l.context,d=n.contextType;typeof d=="object"&&d!==null?d=nt(d):(d=$e(n)?er:Re.current,d=zr(e,d));var k=n.getDerivedStateFromProps,S=typeof k=="function"||typeof l.getSnapshotBeforeUpdate=="function";S||typeof l.UNSAFE_componentWillReceiveProps!="function"&&typeof l.componentWillReceiveProps!="function"||(u!==r||h!==d)&&Nf(e,l,r,d),an=!1;var E=e.memoizedState;l.state=E,Uo(e,r,l,i),h=e.memoizedState,u!==r||E!==h||ze.current||an?(typeof k=="function"&&(ou(e,n,k,r),h=e.memoizedState),(u=an||Rf(e,n,u,r,E,h,d))?(S||typeof l.UNSAFE_componentWillMount!="function"&&typeof l.componentWillMount!="function"||(typeof l.componentWillMount=="function"&&l.componentWillMount(),typeof l.UNSAFE_componentWillMount=="function"&&l.UNSAFE_componentWillMount()),typeof l.componentDidMount=="function"&&(e.flags|=4194308)):(typeof l.componentDidMount=="function"&&(e.flags|=4194308),e.memoizedProps=r,e.memoizedState=h),l.props=r,l.state=h,l.context=d,r=u):(typeof l.componentDidMount=="function"&&(e.flags|=4194308),r=!1)}else{l=e.stateNode,cg(t,e),u=e.memoizedProps,d=e.type===e.elementType?u:ot(e.type,u),l.props=d,S=e.pendingProps,E=l.context,h=n.contextType,typeof h=="object"&&h!==null?h=nt(h):(h=$e(n)?er:Re.current,h=zr(e,h));var N=n.getDerivedStateFromProps;(k=typeof N=="function"||typeof l.getSnapshotBeforeUpdate=="function")||typeof l.UNSAFE_componentWillReceiveProps!="function"&&typeof l.componentWillReceiveProps!="function"||(u!==S||E!==h)&&Nf(e,l,r,h),an=!1,E=e.memoizedState,l.state=E,Uo(e,r,l,i);var O=e.memoizedState;u!==S||E!==O||ze.current||an?(typeof N=="function"&&(ou(e,n,N,r),O=e.memoizedState),(d=an||Rf(e,n,d,r,E,O,h)||!1)?(k||typeof l.UNSAFE_componentWillUpdate!="function"&&typeof l.componentWillUpdate!="function"||(typeof l.componentWillUpdate=="function"&&l.componentWillUpdate(r,O,h),typeof l.UNSAFE_componentWillUpdate=="function"&&l.UNSAFE_componentWillUpdate(r,O,h)),typeof l.componentDidUpdate=="function"&&(e.flags|=4),typeof l.getSnapshotBeforeUpdate=="function"&&(e.flags|=1024)):(typeof l.componentDidUpdate!="function"||u===t.memoizedProps&&E===t.memoizedState||(e.flags|=4),typeof l.getSnapshotBeforeUpdate!="function"||u===t.memoizedProps&&E===t.memoizedState||(e.flags|=1024),e.memoizedProps=r,e.memoizedState=O),l.props=r,l.state=O,l.context=h,r=d):(typeof l.componentDidUpdate!="function"||u===t.memoizedProps&&E===t.memoizedState||(e.flags|=4),typeof l.getSnapshotBeforeUpdate!="function"||u===t.memoizedProps&&E===t.memoizedState||(e.flags|=1024),r=!1)}return cu(t,e,n,r,o,i)}function cu(t,e,n,r,i,o){Ug(t,e);var l=(e.flags&128)!==0;if(!r&&!l)return i&&Ef(e,n,!1),Ht(t,e,o);r=e.stateNode,B_.current=e;var u=l&&typeof n.getDerivedStateFromError!="function"?null:r.render();return e.flags|=1,t!==null&&l?(e.child=br(e,t.child,null,o),e.child=br(e,null,u,o)):De(t,e,u,o),e.memoizedState=r.state,i&&Ef(e,n,!0),e.child}function Fg(t){var e=t.stateNode;e.pendingContext?wf(t,e.pendingContext,e.pendingContext!==e.context):e.context&&wf(t,e.context,!1),lc(t,e.containerInfo)}function Ff(t,e,n,r,i){return $r(),tc(i),e.flags|=256,De(t,e,n,r),e.child}var hu={dehydrated:null,treeContext:null,retryLane:0};function fu(t){return{baseLanes:t,cachePool:null,transitions:null}}function jg(t,e,n){var r=e.pendingProps,i=se.current,o=!1,l=(e.flags&128)!==0,u;if((u=l)||(u=t!==null&&t.memoizedState===null?!1:(i&2)!==0),u?(o=!0,e.flags&=-129):(t===null||t.memoizedState!==null)&&(i|=1),Z(se,i&1),t===null)return iu(e),t=e.memoizedState,t!==null&&(t=t.dehydrated,t!==null)?(e.mode&1?t.data==="$!"?e.lanes=8:e.lanes=1073741824:e.lanes=1,null):(l=r.children,t=r.fallback,o?(r=e.mode,o=e.child,l={mode:"hidden",children:l},!(r&1)&&o!==null?(o.childLanes=0,o.pendingProps=l):o=hl(l,r,0,null),t=Jn(t,r,n,null),o.return=e,t.return=e,o.sibling=t,e.child=o,e.child.memoizedState=fu(n),e.memoizedState=hu,t):gc(e,l));if(i=t.memoizedState,i!==null&&(u=i.dehydrated,u!==null))return H_(t,e,l,r,u,i,n);if(o){o=r.fallback,l=e.mode,i=t.child,u=i.sibling;var h={mode:"hidden",children:r.children};return!(l&1)&&e.child!==i?(r=e.child,r.childLanes=0,r.pendingProps=h,e.deletions=null):(r=In(i,h),r.subtreeFlags=i.subtreeFlags&14680064),u!==null?o=In(u,o):(o=Jn(o,l,n,null),o.flags|=2),o.return=e,r.return=e,r.sibling=o,e.child=r,r=o,o=e.child,l=t.child.memoizedState,l=l===null?fu(n):{baseLanes:l.baseLanes|n,cachePool:null,transitions:l.transitions},o.memoizedState=l,o.childLanes=t.childLanes&~n,e.memoizedState=hu,r}return o=t.child,t=o.sibling,r=In(o,{mode:"visible",children:r.children}),!(e.mode&1)&&(r.lanes=n),r.return=e,r.sibling=null,t!==null&&(n=e.deletions,n===null?(e.deletions=[t],e.flags|=16):n.push(t)),e.child=r,e.memoizedState=null,r}function gc(t,e){return e=hl({mode:"visible",children:e},t.mode,0,null),e.return=t,t.child=e}function Js(t,e,n,r){return r!==null&&tc(r),br(e,t.child,null,n),t=gc(e,e.pendingProps.children),t.flags|=2,e.memoizedState=null,t}function H_(t,e,n,r,i,o,l){if(n)return e.flags&256?(e.flags&=-257,r=da(Error(D(422))),Js(t,e,l,r)):e.memoizedState!==null?(e.child=t.child,e.flags|=128,null):(o=r.fallback,i=e.mode,r=hl({mode:"visible",children:r.children},i,0,null),o=Jn(o,i,l,null),o.flags|=2,r.return=e,o.return=e,r.sibling=o,e.child=r,e.mode&1&&br(e,t.child,null,l),e.child.memoizedState=fu(l),e.memoizedState=hu,o);if(!(e.mode&1))return Js(t,e,l,null);if(i.data==="$!"){if(r=i.nextSibling&&i.nextSibling.dataset,r)var u=r.dgst;return r=u,o=Error(D(419)),r=da(o,r,void 0),Js(t,e,l,r)}if(u=(l&t.childLanes)!==0,Ve||u){if(r=_e,r!==null){switch(l&-l){case 4:i=2;break;case 16:i=8;break;case 64:case 128:case 256:case 512:case 1024:case 2048:case 4096:case 8192:case 16384:case 32768:case 65536:case 131072:case 262144:case 524288:case 1048576:case 2097152:case 4194304:case 8388608:case 16777216:case 33554432:case 67108864:i=32;break;case 536870912:i=268435456;break;default:i=0}i=i&(r.suspendedLanes|l)?0:i,i!==0&&i!==o.retryLane&&(o.retryLane=i,Bt(t,i),dt(r,t,i,-1))}return Ec(),r=da(Error(D(421))),Js(t,e,l,r)}return i.data==="$?"?(e.flags|=128,e.child=t.child,e=r0.bind(null,t),i._reactRetry=e,null):(t=o.treeContext,We=_n(i.nextSibling),Ge=e,ie=!0,at=null,t!==null&&(Ye[Ze++]=Ut,Ye[Ze++]=Ft,Ye[Ze++]=tr,Ut=t.id,Ft=t.overflow,tr=e),e=gc(e,r.children),e.flags|=4096,e)}function jf(t,e,n){t.lanes|=e;var r=t.alternate;r!==null&&(r.lanes|=e),su(t.return,e,n)}function pa(t,e,n,r,i){var o=t.memoizedState;o===null?t.memoizedState={isBackwards:e,rendering:null,renderingStartTime:0,last:r,tail:n,tailMode:i}:(o.isBackwards=e,o.rendering=null,o.renderingStartTime=0,o.last=r,o.tail=n,o.tailMode=i)}function Vg(t,e,n){var r=e.pendingProps,i=r.revealOrder,o=r.tail;if(De(t,e,r.children,n),r=se.current,r&2)r=r&1|2,e.flags|=128;else{if(t!==null&&t.flags&128)e:for(t=e.child;t!==null;){if(t.tag===13)t.memoizedState!==null&&jf(t,n,e);else if(t.tag===19)jf(t,n,e);else if(t.child!==null){t.child.return=t,t=t.child;continue}if(t===e)break e;for(;t.sibling===null;){if(t.return===null||t.return===e)break e;t=t.return}t.sibling.return=t.return,t=t.sibling}r&=1}if(Z(se,r),!(e.mode&1))e.memoizedState=null;else switch(i){case"forwards":for(n=e.child,i=null;n!==null;)t=n.alternate,t!==null&&Fo(t)===null&&(i=n),n=n.sibling;n=i,n===null?(i=e.child,e.child=null):(i=n.sibling,n.sibling=null),pa(e,!1,i,n,o);break;case"backwards":for(n=null,i=e.child,e.child=null;i!==null;){if(t=i.alternate,t!==null&&Fo(t)===null){e.child=i;break}t=i.sibling,i.sibling=n,n=i,i=t}pa(e,!0,n,null,o);break;case"together":pa(e,!1,null,null,void 0);break;default:e.memoizedState=null}return e.child}function ho(t,e){!(e.mode&1)&&t!==null&&(t.alternate=null,e.alternate=null,e.flags|=2)}function Ht(t,e,n){if(t!==null&&(e.dependencies=t.dependencies),rr|=e.lanes,!(n&e.childLanes))return null;if(t!==null&&e.child!==t.child)throw Error(D(153));if(e.child!==null){for(t=e.child,n=In(t,t.pendingProps),e.child=n,n.return=e;t.sibling!==null;)t=t.sibling,n=n.sibling=In(t,t.pendingProps),n.return=e;n.sibling=null}return e.child}function W_(t,e,n){switch(e.tag){case 3:Fg(e),$r();break;case 5:hg(e);break;case 1:$e(e.type)&&Oo(e);break;case 4:lc(e,e.stateNode.containerInfo);break;case 10:var r=e.type._context,i=e.memoizedProps.value;Z(xo,r._currentValue),r._currentValue=i;break;case 13:if(r=e.memoizedState,r!==null)return r.dehydrated!==null?(Z(se,se.current&1),e.flags|=128,null):n&e.child.childLanes?jg(t,e,n):(Z(se,se.current&1),t=Ht(t,e,n),t!==null?t.sibling:null);Z(se,se.current&1);break;case 19:if(r=(n&e.childLanes)!==0,t.flags&128){if(r)return Vg(t,e,n);e.flags|=128}if(i=e.memoizedState,i!==null&&(i.rendering=null,i.tail=null,i.lastEffect=null),Z(se,se.current),r)break;return null;case 22:case 23:return e.lanes=0,Mg(t,e,n)}return Ht(t,e,n)}var zg,du,$g,bg;zg=function(t,e){for(var n=e.child;n!==null;){if(n.tag===5||n.tag===6)t.appendChild(n.stateNode);else if(n.tag!==4&&n.child!==null){n.child.return=n,n=n.child;continue}if(n===e)break;for(;n.sibling===null;){if(n.return===null||n.return===e)return;n=n.return}n.sibling.return=n.return,n=n.sibling}};du=function(){};$g=function(t,e,n,r){var i=t.memoizedProps;if(i!==r){t=e.stateNode,Kn(Ct.current);var o=null;switch(n){case"input":i=Ma(t,i),r=Ma(t,r),o=[];break;case"select":i=le({},i,{value:void 0}),r=le({},r,{value:void 0}),o=[];break;case"textarea":i=ja(t,i),r=ja(t,r),o=[];break;default:typeof i.onClick!="function"&&typeof r.onClick=="function"&&(t.onclick=Ro)}za(n,r);var l;n=null;for(d in i)if(!r.hasOwnProperty(d)&&i.hasOwnProperty(d)&&i[d]!=null)if(d==="style"){var u=i[d];for(l in u)u.hasOwnProperty(l)&&(n||(n={}),n[l]="")}else d!=="dangerouslySetInnerHTML"&&d!=="children"&&d!=="suppressContentEditableWarning"&&d!=="suppressHydrationWarning"&&d!=="autoFocus"&&(Xi.hasOwnProperty(d)?o||(o=[]):(o=o||[]).push(d,null));for(d in r){var h=r[d];if(u=i!=null?i[d]:void 0,r.hasOwnProperty(d)&&h!==u&&(h!=null||u!=null))if(d==="style")if(u){for(l in u)!u.hasOwnProperty(l)||h&&h.hasOwnProperty(l)||(n||(n={}),n[l]="");for(l in h)h.hasOwnProperty(l)&&u[l]!==h[l]&&(n||(n={}),n[l]=h[l])}else n||(o||(o=[]),o.push(d,n)),n=h;else d==="dangerouslySetInnerHTML"?(h=h?h.__html:void 0,u=u?u.__html:void 0,h!=null&&u!==h&&(o=o||[]).push(d,h)):d==="children"?typeof h!="string"&&typeof h!="number"||(o=o||[]).push(d,""+h):d!=="suppressContentEditableWarning"&&d!=="suppressHydrationWarning"&&(Xi.hasOwnProperty(d)?(h!=null&&d==="onScroll"&&te("scroll",t),o||u===h||(o=[])):(o=o||[]).push(d,h))}n&&(o=o||[]).push("style",n);var d=o;(e.updateQueue=d)&&(e.flags|=4)}};bg=function(t,e,n,r){n!==r&&(e.flags|=4)};function Ci(t,e){if(!ie)switch(t.tailMode){case"hidden":e=t.tail;for(var n=null;e!==null;)e.alternate!==null&&(n=e),e=e.sibling;n===null?t.tail=null:n.sibling=null;break;case"collapsed":n=t.tail;for(var r=null;n!==null;)n.alternate!==null&&(r=n),n=n.sibling;r===null?e||t.tail===null?t.tail=null:t.tail.sibling=null:r.sibling=null}}function Ce(t){var e=t.alternate!==null&&t.alternate.child===t.child,n=0,r=0;if(e)for(var i=t.child;i!==null;)n|=i.lanes|i.childLanes,r|=i.subtreeFlags&14680064,r|=i.flags&14680064,i.return=t,i=i.sibling;else for(i=t.child;i!==null;)n|=i.lanes|i.childLanes,r|=i.subtreeFlags,r|=i.flags,i.return=t,i=i.sibling;return t.subtreeFlags|=r,t.childLanes=n,e}function G_(t,e,n){var r=e.pendingProps;switch(ec(e),e.tag){case 2:case 16:case 15:case 0:case 11:case 7:case 8:case 12:case 9:case 14:return Ce(e),null;case 1:return $e(e.type)&&No(),Ce(e),null;case 3:return r=e.stateNode,Br(),ne(ze),ne(Re),uc(),r.pendingContext&&(r.context=r.pendingContext,r.pendingContext=null),(t===null||t.child===null)&&(qs(e)?e.flags|=4:t===null||t.memoizedState.isDehydrated&&!(e.flags&256)||(e.flags|=1024,at!==null&&(Eu(at),at=null))),du(t,e),Ce(e),null;case 5:ac(e);var i=Kn(ls.current);if(n=e.type,t!==null&&e.stateNode!=null)$g(t,e,n,r,i),t.ref!==e.ref&&(e.flags|=512,e.flags|=2097152);else{if(!r){if(e.stateNode===null)throw Error(D(166));return Ce(e),null}if(t=Kn(Ct.current),qs(e)){r=e.stateNode,n=e.type;var o=e.memoizedProps;switch(r[St]=e,r[ss]=o,t=(e.mode&1)!==0,n){case"dialog":te("cancel",r),te("close",r);break;case"iframe":case"object":case"embed":te("load",r);break;case"video":case"audio":for(i=0;i<Oi.length;i++)te(Oi[i],r);break;case"source":te("error",r);break;case"img":case"image":case"link":te("error",r),te("load",r);break;case"details":te("toggle",r);break;case"input":Gh(r,o),te("invalid",r);break;case"select":r._wrapperState={wasMultiple:!!o.multiple},te("invalid",r);break;case"textarea":qh(r,o),te("invalid",r)}za(n,o),i=null;for(var l in o)if(o.hasOwnProperty(l)){var u=o[l];l==="children"?typeof u=="string"?r.textContent!==u&&(o.suppressHydrationWarning!==!0&&Ks(r.textContent,u,t),i=["children",u]):typeof u=="number"&&r.textContent!==""+u&&(o.suppressHydrationWarning!==!0&&Ks(r.textContent,u,t),i=["children",""+u]):Xi.hasOwnProperty(l)&&u!=null&&l==="onScroll"&&te("scroll",r)}switch(n){case"input":Vs(r),Kh(r,o,!0);break;case"textarea":Vs(r),Xh(r);break;case"select":case"option":break;default:typeof o.onClick=="function"&&(r.onclick=Ro)}r=i,e.updateQueue=r,r!==null&&(e.flags|=4)}else{l=i.nodeType===9?i:i.ownerDocument,t==="http://www.w3.org/1999/xhtml"&&(t=mp(n)),t==="http://www.w3.org/1999/xhtml"?n==="script"?(t=l.createElement("div"),t.innerHTML="<script><\/script>",t=t.removeChild(t.firstChild)):typeof r.is=="string"?t=l.createElement(n,{is:r.is}):(t=l.createElement(n),n==="select"&&(l=t,r.multiple?l.multiple=!0:r.size&&(l.size=r.size))):t=l.createElementNS(t,n),t[St]=e,t[ss]=r,zg(t,e,!1,!1),e.stateNode=t;e:{switch(l=$a(n,r),n){case"dialog":te("cancel",t),te("close",t),i=r;break;case"iframe":case"object":case"embed":te("load",t),i=r;break;case"video":case"audio":for(i=0;i<Oi.length;i++)te(Oi[i],t);i=r;break;case"source":te("error",t),i=r;break;case"img":case"image":case"link":te("error",t),te("load",t),i=r;break;case"details":te("toggle",t),i=r;break;case"input":Gh(t,r),i=Ma(t,r),te("invalid",t);break;case"option":i=r;break;case"select":t._wrapperState={wasMultiple:!!r.multiple},i=le({},r,{value:void 0}),te("invalid",t);break;case"textarea":qh(t,r),i=ja(t,r),te("invalid",t);break;default:i=r}za(n,i),u=i;for(o in u)if(u.hasOwnProperty(o)){var h=u[o];o==="style"?_p(t,h):o==="dangerouslySetInnerHTML"?(h=h?h.__html:void 0,h!=null&&yp(t,h)):o==="children"?typeof h=="string"?(n!=="textarea"||h!=="")&&Ji(t,h):typeof h=="number"&&Ji(t,""+h):o!=="suppressContentEditableWarning"&&o!=="suppressHydrationWarning"&&o!=="autoFocus"&&(Xi.hasOwnProperty(o)?h!=null&&o==="onScroll"&&te("scroll",t):h!=null&&Vu(t,o,h,l))}switch(n){case"input":Vs(t),Kh(t,r,!1);break;case"textarea":Vs(t),Xh(t);break;case"option":r.value!=null&&t.setAttribute("value",""+Pn(r.value));break;case"select":t.multiple=!!r.multiple,o=r.value,o!=null?Rr(t,!!r.multiple,o,!1):r.defaultValue!=null&&Rr(t,!!r.multiple,r.defaultValue,!0);break;default:typeof i.onClick=="function"&&(t.onclick=Ro)}switch(n){case"button":case"input":case"select":case"textarea":r=!!r.autoFocus;break e;case"img":r=!0;break e;default:r=!1}}r&&(e.flags|=4)}e.ref!==null&&(e.flags|=512,e.flags|=2097152)}return Ce(e),null;case 6:if(t&&e.stateNode!=null)bg(t,e,t.memoizedProps,r);else{if(typeof r!="string"&&e.stateNode===null)throw Error(D(166));if(n=Kn(ls.current),Kn(Ct.current),qs(e)){if(r=e.stateNode,n=e.memoizedProps,r[St]=e,(o=r.nodeValue!==n)&&(t=Ge,t!==null))switch(t.tag){case 3:Ks(r.nodeValue,n,(t.mode&1)!==0);break;case 5:t.memoizedProps.suppressHydrationWarning!==!0&&Ks(r.nodeValue,n,(t.mode&1)!==0)}o&&(e.flags|=4)}else r=(n.nodeType===9?n:n.ownerDocument).createTextNode(r),r[St]=e,e.stateNode=r}return Ce(e),null;case 13:if(ne(se),r=e.memoizedState,t===null||t.memoizedState!==null&&t.memoizedState.dehydrated!==null){if(ie&&We!==null&&e.mode&1&&!(e.flags&128))og(),$r(),e.flags|=98560,o=!1;else if(o=qs(e),r!==null&&r.dehydrated!==null){if(t===null){if(!o)throw Error(D(318));if(o=e.memoizedState,o=o!==null?o.dehydrated:null,!o)throw Error(D(317));o[St]=e}else $r(),!(e.flags&128)&&(e.memoizedState=null),e.flags|=4;Ce(e),o=!1}else at!==null&&(Eu(at),at=null),o=!0;if(!o)return e.flags&65536?e:null}return e.flags&128?(e.lanes=n,e):(r=r!==null,r!==(t!==null&&t.memoizedState!==null)&&r&&(e.child.flags|=8192,e.mode&1&&(t===null||se.current&1?me===0&&(me=3):Ec())),e.updateQueue!==null&&(e.flags|=4),Ce(e),null);case 4:return Br(),du(t,e),t===null&&rs(e.stateNode.containerInfo),Ce(e),null;case 10:return ic(e.type._context),Ce(e),null;case 17:return $e(e.type)&&No(),Ce(e),null;case 19:if(ne(se),o=e.memoizedState,o===null)return Ce(e),null;if(r=(e.flags&128)!==0,l=o.rendering,l===null)if(r)Ci(o,!1);else{if(me!==0||t!==null&&t.flags&128)for(t=e.child;t!==null;){if(l=Fo(t),l!==null){for(e.flags|=128,Ci(o,!1),r=l.updateQueue,r!==null&&(e.updateQueue=r,e.flags|=4),e.subtreeFlags=0,r=n,n=e.child;n!==null;)o=n,t=r,o.flags&=14680066,l=o.alternate,l===null?(o.childLanes=0,o.lanes=t,o.child=null,o.subtreeFlags=0,o.memoizedProps=null,o.memoizedState=null,o.updateQueue=null,o.dependencies=null,o.stateNode=null):(o.childLanes=l.childLanes,o.lanes=l.lanes,o.child=l.child,o.subtreeFlags=0,o.deletions=null,o.memoizedProps=l.memoizedProps,o.memoizedState=l.memoizedState,o.updateQueue=l.updateQueue,o.type=l.type,t=l.dependencies,o.dependencies=t===null?null:{lanes:t.lanes,firstContext:t.firstContext}),n=n.sibling;return Z(se,se.current&1|2),e.child}t=t.sibling}o.tail!==null&&he()>Wr&&(e.flags|=128,r=!0,Ci(o,!1),e.lanes=4194304)}else{if(!r)if(t=Fo(l),t!==null){if(e.flags|=128,r=!0,n=t.updateQueue,n!==null&&(e.updateQueue=n,e.flags|=4),Ci(o,!0),o.tail===null&&o.tailMode==="hidden"&&!l.alternate&&!ie)return Ce(e),null}else 2*he()-o.renderingStartTime>Wr&&n!==1073741824&&(e.flags|=128,r=!0,Ci(o,!1),e.lanes=4194304);o.isBackwards?(l.sibling=e.child,e.child=l):(n=o.last,n!==null?n.sibling=l:e.child=l,o.last=l)}return o.tail!==null?(e=o.tail,o.rendering=e,o.tail=e.sibling,o.renderingStartTime=he(),e.sibling=null,n=se.current,Z(se,r?n&1|2:n&1),e):(Ce(e),null);case 22:case 23:return wc(),r=e.memoizedState!==null,t!==null&&t.memoizedState!==null!==r&&(e.flags|=8192),r&&e.mode&1?He&1073741824&&(Ce(e),e.subtreeFlags&6&&(e.flags|=8192)):Ce(e),null;case 24:return null;case 25:return null}throw Error(D(156,e.tag))}function K_(t,e){switch(ec(e),e.tag){case 1:return $e(e.type)&&No(),t=e.flags,t&65536?(e.flags=t&-65537|128,e):null;case 3:return Br(),ne(ze),ne(Re),uc(),t=e.flags,t&65536&&!(t&128)?(e.flags=t&-65537|128,e):null;case 5:return ac(e),null;case 13:if(ne(se),t=e.memoizedState,t!==null&&t.dehydrated!==null){if(e.alternate===null)throw Error(D(340));$r()}return t=e.flags,t&65536?(e.flags=t&-65537|128,e):null;case 19:return ne(se),null;case 4:return Br(),null;case 10:return ic(e.type._context),null;case 22:case 23:return wc(),null;case 24:return null;default:return null}}var Qs=!1,Ae=!1,q_=typeof WeakSet=="function"?WeakSet:Set,j=null;function Cr(t,e){var n=t.ref;if(n!==null)if(typeof n=="function")try{n(null)}catch(r){ae(t,e,r)}else n.current=null}function pu(t,e,n){try{n()}catch(r){ae(t,e,r)}}var Vf=!1;function X_(t,e){if(Qa=Co,t=Kp(),Yu(t)){if("selectionStart"in t)var n={start:t.selectionStart,end:t.selectionEnd};else e:{n=(n=t.ownerDocument)&&n.defaultView||window;var r=n.getSelection&&n.getSelection();if(r&&r.rangeCount!==0){n=r.anchorNode;var i=r.anchorOffset,o=r.focusNode;r=r.focusOffset;try{n.nodeType,o.nodeType}catch{n=null;break e}var l=0,u=-1,h=-1,d=0,k=0,S=t,E=null;t:for(;;){for(var N;S!==n||i!==0&&S.nodeType!==3||(u=l+i),S!==o||r!==0&&S.nodeType!==3||(h=l+r),S.nodeType===3&&(l+=S.nodeValue.length),(N=S.firstChild)!==null;)E=S,S=N;for(;;){if(S===t)break t;if(E===n&&++d===i&&(u=l),E===o&&++k===r&&(h=l),(N=S.nextSibling)!==null)break;S=E,E=S.parentNode}S=N}n=u===-1||h===-1?null:{start:u,end:h}}else n=null}n=n||{start:0,end:0}}else n=null;for(Ya={focusedElem:t,selectionRange:n},Co=!1,j=e;j!==null;)if(e=j,t=e.child,(e.subtreeFlags&1028)!==0&&t!==null)t.return=e,j=t;else for(;j!==null;){e=j;try{var O=e.alternate;if(e.flags&1024)switch(e.tag){case 0:case 11:case 15:break;case 1:if(O!==null){var L=O.memoizedProps,z=O.memoizedState,I=e.stateNode,_=I.getSnapshotBeforeUpdate(e.elementType===e.type?L:ot(e.type,L),z);I.__reactInternalSnapshotBeforeUpdate=_}break;case 3:var T=e.stateNode.containerInfo;T.nodeType===1?T.textContent="":T.nodeType===9&&T.documentElement&&T.removeChild(T.documentElement);break;case 5:case 6:case 4:case 17:break;default:throw Error(D(163))}}catch(R){ae(e,e.return,R)}if(t=e.sibling,t!==null){t.return=e.return,j=t;break}j=e.return}return O=Vf,Vf=!1,O}function zi(t,e,n){var r=e.updateQueue;if(r=r!==null?r.lastEffect:null,r!==null){var i=r=r.next;do{if((i.tag&t)===t){var o=i.destroy;i.destroy=void 0,o!==void 0&&pu(e,n,o)}i=i.next}while(i!==r)}}function ul(t,e){if(e=e.updateQueue,e=e!==null?e.lastEffect:null,e!==null){var n=e=e.next;do{if((n.tag&t)===t){var r=n.create;n.destroy=r()}n=n.next}while(n!==e)}}function gu(t){var e=t.ref;if(e!==null){var n=t.stateNode;switch(t.tag){case 5:t=n;break;default:t=n}typeof e=="function"?e(t):e.current=t}}function Bg(t){var e=t.alternate;e!==null&&(t.alternate=null,Bg(e)),t.child=null,t.deletions=null,t.sibling=null,t.tag===5&&(e=t.stateNode,e!==null&&(delete e[St],delete e[ss],delete e[tu],delete e[O_],delete e[D_])),t.stateNode=null,t.return=null,t.dependencies=null,t.memoizedProps=null,t.memoizedState=null,t.pendingProps=null,t.stateNode=null,t.updateQueue=null}function Hg(t){return t.tag===5||t.tag===3||t.tag===4}function zf(t){e:for(;;){for(;t.sibling===null;){if(t.return===null||Hg(t.return))return null;t=t.return}for(t.sibling.return=t.return,t=t.sibling;t.tag!==5&&t.tag!==6&&t.tag!==18;){if(t.flags&2||t.child===null||t.tag===4)continue e;t.child.return=t,t=t.child}if(!(t.flags&2))return t.stateNode}}function mu(t,e,n){var r=t.tag;if(r===5||r===6)t=t.stateNode,e?n.nodeType===8?n.parentNode.insertBefore(t,e):n.insertBefore(t,e):(n.nodeType===8?(e=n.parentNode,e.insertBefore(t,n)):(e=n,e.appendChild(t)),n=n._reactRootContainer,n!=null||e.onclick!==null||(e.onclick=Ro));else if(r!==4&&(t=t.child,t!==null))for(mu(t,e,n),t=t.sibling;t!==null;)mu(t,e,n),t=t.sibling}function yu(t,e,n){var r=t.tag;if(r===5||r===6)t=t.stateNode,e?n.insertBefore(t,e):n.appendChild(t);else if(r!==4&&(t=t.child,t!==null))for(yu(t,e,n),t=t.sibling;t!==null;)yu(t,e,n),t=t.sibling}var Ee=null,lt=!1;function sn(t,e,n){for(n=n.child;n!==null;)Wg(t,e,n),n=n.sibling}function Wg(t,e,n){if(kt&&typeof kt.onCommitFiberUnmount=="function")try{kt.onCommitFiberUnmount(tl,n)}catch{}switch(n.tag){case 5:Ae||Cr(n,e);case 6:var r=Ee,i=lt;Ee=null,sn(t,e,n),Ee=r,lt=i,Ee!==null&&(lt?(t=Ee,n=n.stateNode,t.nodeType===8?t.parentNode.removeChild(n):t.removeChild(n)):Ee.removeChild(n.stateNode));break;case 18:Ee!==null&&(lt?(t=Ee,n=n.stateNode,t.nodeType===8?la(t.parentNode,n):t.nodeType===1&&la(t,n),es(t)):la(Ee,n.stateNode));break;case 4:r=Ee,i=lt,Ee=n.stateNode.containerInfo,lt=!0,sn(t,e,n),Ee=r,lt=i;break;case 0:case 11:case 14:case 15:if(!Ae&&(r=n.updateQueue,r!==null&&(r=r.lastEffect,r!==null))){i=r=r.next;do{var o=i,l=o.destroy;o=o.tag,l!==void 0&&(o&2||o&4)&&pu(n,e,l),i=i.next}while(i!==r)}sn(t,e,n);break;case 1:if(!Ae&&(Cr(n,e),r=n.stateNode,typeof r.componentWillUnmount=="function"))try{r.props=n.memoizedProps,r.state=n.memoizedState,r.componentWillUnmount()}catch(u){ae(n,e,u)}sn(t,e,n);break;case 21:sn(t,e,n);break;case 22:n.mode&1?(Ae=(r=Ae)||n.memoizedState!==null,sn(t,e,n),Ae=r):sn(t,e,n);break;default:sn(t,e,n)}}function $f(t){var e=t.updateQueue;if(e!==null){t.updateQueue=null;var n=t.stateNode;n===null&&(n=t.stateNode=new q_),e.forEach(function(r){var i=i0.bind(null,t,r);n.has(r)||(n.add(r),r.then(i,i))})}}function st(t,e){var n=e.deletions;if(n!==null)for(var r=0;r<n.length;r++){var i=n[r];try{var o=t,l=e,u=l;e:for(;u!==null;){switch(u.tag){case 5:Ee=u.stateNode,lt=!1;break e;case 3:Ee=u.stateNode.containerInfo,lt=!0;break e;case 4:Ee=u.stateNode.containerInfo,lt=!0;break e}u=u.return}if(Ee===null)throw Error(D(160));Wg(o,l,i),Ee=null,lt=!1;var h=i.alternate;h!==null&&(h.return=null),i.return=null}catch(d){ae(i,e,d)}}if(e.subtreeFlags&12854)for(e=e.child;e!==null;)Gg(e,t),e=e.sibling}function Gg(t,e){var n=t.alternate,r=t.flags;switch(t.tag){case 0:case 11:case 14:case 15:if(st(e,t),vt(t),r&4){try{zi(3,t,t.return),ul(3,t)}catch(L){ae(t,t.return,L)}try{zi(5,t,t.return)}catch(L){ae(t,t.return,L)}}break;case 1:st(e,t),vt(t),r&512&&n!==null&&Cr(n,n.return);break;case 5:if(st(e,t),vt(t),r&512&&n!==null&&Cr(n,n.return),t.flags&32){var i=t.stateNode;try{Ji(i,"")}catch(L){ae(t,t.return,L)}}if(r&4&&(i=t.stateNode,i!=null)){var o=t.memoizedProps,l=n!==null?n.memoizedProps:o,u=t.type,h=t.updateQueue;if(t.updateQueue=null,h!==null)try{u==="input"&&o.type==="radio"&&o.name!=null&&pp(i,o),$a(u,l);var d=$a(u,o);for(l=0;l<h.length;l+=2){var k=h[l],S=h[l+1];k==="style"?_p(i,S):k==="dangerouslySetInnerHTML"?yp(i,S):k==="children"?Ji(i,S):Vu(i,k,S,d)}switch(u){case"input":Ua(i,o);break;case"textarea":gp(i,o);break;case"select":var E=i._wrapperState.wasMultiple;i._wrapperState.wasMultiple=!!o.multiple;var N=o.value;N!=null?Rr(i,!!o.multiple,N,!1):E!==!!o.multiple&&(o.defaultValue!=null?Rr(i,!!o.multiple,o.defaultValue,!0):Rr(i,!!o.multiple,o.multiple?[]:"",!1))}i[ss]=o}catch(L){ae(t,t.return,L)}}break;case 6:if(st(e,t),vt(t),r&4){if(t.stateNode===null)throw Error(D(162));i=t.stateNode,o=t.memoizedProps;try{i.nodeValue=o}catch(L){ae(t,t.return,L)}}break;case 3:if(st(e,t),vt(t),r&4&&n!==null&&n.memoizedState.isDehydrated)try{es(e.containerInfo)}catch(L){ae(t,t.return,L)}break;case 4:st(e,t),vt(t);break;case 13:st(e,t),vt(t),i=t.child,i.flags&8192&&(o=i.memoizedState!==null,i.stateNode.isHidden=o,!o||i.alternate!==null&&i.alternate.memoizedState!==null||(vc=he())),r&4&&$f(t);break;case 22:if(k=n!==null&&n.memoizedState!==null,t.mode&1?(Ae=(d=Ae)||k,st(e,t),Ae=d):st(e,t),vt(t),r&8192){if(d=t.memoizedState!==null,(t.stateNode.isHidden=d)&&!k&&t.mode&1)for(j=t,k=t.child;k!==null;){for(S=j=k;j!==null;){switch(E=j,N=E.child,E.tag){case 0:case 11:case 14:case 15:zi(4,E,E.return);break;case 1:Cr(E,E.return);var O=E.stateNode;if(typeof O.componentWillUnmount=="function"){r=E,n=E.return;try{e=r,O.props=e.memoizedProps,O.state=e.memoizedState,O.componentWillUnmount()}catch(L){ae(r,n,L)}}break;case 5:Cr(E,E.return);break;case 22:if(E.memoizedState!==null){Bf(S);continue}}N!==null?(N.return=E,j=N):Bf(S)}k=k.sibling}e:for(k=null,S=t;;){if(S.tag===5){if(k===null){k=S;try{i=S.stateNode,d?(o=i.style,typeof o.setProperty=="function"?o.setProperty("display","none","important"):o.display="none"):(u=S.stateNode,h=S.memoizedProps.style,l=h!=null&&h.hasOwnProperty("display")?h.display:null,u.style.display=vp("display",l))}catch(L){ae(t,t.return,L)}}}else if(S.tag===6){if(k===null)try{S.stateNode.nodeValue=d?"":S.memoizedProps}catch(L){ae(t,t.return,L)}}else if((S.tag!==22&&S.tag!==23||S.memoizedState===null||S===t)&&S.child!==null){S.child.return=S,S=S.child;continue}if(S===t)break e;for(;S.sibling===null;){if(S.return===null||S.return===t)break e;k===S&&(k=null),S=S.return}k===S&&(k=null),S.sibling.return=S.return,S=S.sibling}}break;case 19:st(e,t),vt(t),r&4&&$f(t);break;case 21:break;default:st(e,t),vt(t)}}function vt(t){var e=t.flags;if(e&2){try{e:{for(var n=t.return;n!==null;){if(Hg(n)){var r=n;break e}n=n.return}throw Error(D(160))}switch(r.tag){case 5:var i=r.stateNode;r.flags&32&&(Ji(i,""),r.flags&=-33);var o=zf(t);yu(t,o,i);break;case 3:case 4:var l=r.stateNode.containerInfo,u=zf(t);mu(t,u,l);break;default:throw Error(D(161))}}catch(h){ae(t,t.return,h)}t.flags&=-3}e&4096&&(t.flags&=-4097)}function J_(t,e,n){j=t,Kg(t)}function Kg(t,e,n){for(var r=(t.mode&1)!==0;j!==null;){var i=j,o=i.child;if(i.tag===22&&r){var l=i.memoizedState!==null||Qs;if(!l){var u=i.alternate,h=u!==null&&u.memoizedState!==null||Ae;u=Qs;var d=Ae;if(Qs=l,(Ae=h)&&!d)for(j=i;j!==null;)l=j,h=l.child,l.tag===22&&l.memoizedState!==null?Hf(i):h!==null?(h.return=l,j=h):Hf(i);for(;o!==null;)j=o,Kg(o),o=o.sibling;j=i,Qs=u,Ae=d}bf(t)}else i.subtreeFlags&8772&&o!==null?(o.return=i,j=o):bf(t)}}function bf(t){for(;j!==null;){var e=j;if(e.flags&8772){var n=e.alternate;try{if(e.flags&8772)switch(e.tag){case 0:case 11:case 15:Ae||ul(5,e);break;case 1:var r=e.stateNode;if(e.flags&4&&!Ae)if(n===null)r.componentDidMount();else{var i=e.elementType===e.type?n.memoizedProps:ot(e.type,n.memoizedProps);r.componentDidUpdate(i,n.memoizedState,r.__reactInternalSnapshotBeforeUpdate)}var o=e.updateQueue;o!==null&&Cf(e,o,r);break;case 3:var l=e.updateQueue;if(l!==null){if(n=null,e.child!==null)switch(e.child.tag){case 5:n=e.child.stateNode;break;case 1:n=e.child.stateNode}Cf(e,l,n)}break;case 5:var u=e.stateNode;if(n===null&&e.flags&4){n=u;var h=e.memoizedProps;switch(e.type){case"button":case"input":case"select":case"textarea":h.autoFocus&&n.focus();break;case"img":h.src&&(n.src=h.src)}}break;case 6:break;case 4:break;case 12:break;case 13:if(e.memoizedState===null){var d=e.alternate;if(d!==null){var k=d.memoizedState;if(k!==null){var S=k.dehydrated;S!==null&&es(S)}}}break;case 19:case 17:case 21:case 22:case 23:case 25:break;default:throw Error(D(163))}Ae||e.flags&512&&gu(e)}catch(E){ae(e,e.return,E)}}if(e===t){j=null;break}if(n=e.sibling,n!==null){n.return=e.return,j=n;break}j=e.return}}function Bf(t){for(;j!==null;){var e=j;if(e===t){j=null;break}var n=e.sibling;if(n!==null){n.return=e.return,j=n;break}j=e.return}}function Hf(t){for(;j!==null;){var e=j;try{switch(e.tag){case 0:case 11:case 15:var n=e.return;try{ul(4,e)}catch(h){ae(e,n,h)}break;case 1:var r=e.stateNode;if(typeof r.componentDidMount=="function"){var i=e.return;try{r.componentDidMount()}catch(h){ae(e,i,h)}}var o=e.return;try{gu(e)}catch(h){ae(e,o,h)}break;case 5:var l=e.return;try{gu(e)}catch(h){ae(e,l,h)}}}catch(h){ae(e,e.return,h)}if(e===t){j=null;break}var u=e.sibling;if(u!==null){u.return=e.return,j=u;break}j=e.return}}var Q_=Math.ceil,zo=Xt.ReactCurrentDispatcher,mc=Xt.ReactCurrentOwner,tt=Xt.ReactCurrentBatchConfig,q=0,_e=null,fe=null,Se=0,He=0,Pr=On(0),me=0,hs=null,rr=0,cl=0,yc=0,$i=null,je=null,vc=0,Wr=1/0,Ot=null,$o=!1,vu=null,En=null,Ys=!1,gn=null,bo=0,bi=0,_u=null,fo=-1,po=0;function xe(){return q&6?he():fo!==-1?fo:fo=he()}function Sn(t){return t.mode&1?q&2&&Se!==0?Se&-Se:x_.transition!==null?(po===0&&(po=Op()),po):(t=Q,t!==0||(t=window.event,t=t===void 0?16:jp(t.type)),t):1}function dt(t,e,n,r){if(50<bi)throw bi=0,_u=null,Error(D(185));ys(t,n,r),(!(q&2)||t!==_e)&&(t===_e&&(!(q&2)&&(cl|=n),me===4&&cn(t,Se)),be(t,r),n===1&&q===0&&!(e.mode&1)&&(Wr=he()+500,ol&&Dn()))}function be(t,e){var n=t.callbackNode;xv(t,e);var r=ko(t,t===_e?Se:0);if(r===0)n!==null&&Yh(n),t.callbackNode=null,t.callbackPriority=0;else if(e=r&-r,t.callbackPriority!==e){if(n!=null&&Yh(n),e===1)t.tag===0?L_(Wf.bind(null,t)):rg(Wf.bind(null,t)),R_(function(){!(q&6)&&Dn()}),n=null;else{switch(Dp(r)){case 1:n=Hu;break;case 4:n=Rp;break;case 16:n=To;break;case 536870912:n=Np;break;default:n=To}n=tm(n,qg.bind(null,t))}t.callbackPriority=e,t.callbackNode=n}}function qg(t,e){if(fo=-1,po=0,q&6)throw Error(D(327));var n=t.callbackNode;if(xr()&&t.callbackNode!==n)return null;var r=ko(t,t===_e?Se:0);if(r===0)return null;if(r&30||r&t.expiredLanes||e)e=Bo(t,r);else{e=r;var i=q;q|=2;var o=Jg();(_e!==t||Se!==e)&&(Ot=null,Wr=he()+500,Xn(t,e));do try{e0();break}catch(u){Xg(t,u)}while(!0);rc(),zo.current=o,q=i,fe!==null?e=0:(_e=null,Se=0,e=me)}if(e!==0){if(e===2&&(i=Ga(t),i!==0&&(r=i,e=wu(t,i))),e===1)throw n=hs,Xn(t,0),cn(t,r),be(t,he()),n;if(e===6)cn(t,r);else{if(i=t.current.alternate,!(r&30)&&!Y_(i)&&(e=Bo(t,r),e===2&&(o=Ga(t),o!==0&&(r=o,e=wu(t,o))),e===1))throw n=hs,Xn(t,0),cn(t,r),be(t,he()),n;switch(t.finishedWork=i,t.finishedLanes=r,e){case 0:case 1:throw Error(D(345));case 2:bn(t,je,Ot);break;case 3:if(cn(t,r),(r&130023424)===r&&(e=vc+500-he(),10<e)){if(ko(t,0)!==0)break;if(i=t.suspendedLanes,(i&r)!==r){xe(),t.pingedLanes|=t.suspendedLanes&i;break}t.timeoutHandle=eu(bn.bind(null,t,je,Ot),e);break}bn(t,je,Ot);break;case 4:if(cn(t,r),(r&4194240)===r)break;for(e=t.eventTimes,i=-1;0<r;){var l=31-ft(r);o=1<<l,l=e[l],l>i&&(i=l),r&=~o}if(r=i,r=he()-r,r=(120>r?120:480>r?480:1080>r?1080:1920>r?1920:3e3>r?3e3:4320>r?4320:1960*Q_(r/1960))-r,10<r){t.timeoutHandle=eu(bn.bind(null,t,je,Ot),r);break}bn(t,je,Ot);break;case 5:bn(t,je,Ot);break;default:throw Error(D(329))}}}return be(t,he()),t.callbackNode===n?qg.bind(null,t):null}function wu(t,e){var n=$i;return t.current.memoizedState.isDehydrated&&(Xn(t,e).flags|=256),t=Bo(t,e),t!==2&&(e=je,je=n,e!==null&&Eu(e)),t}function Eu(t){je===null?je=t:je.push.apply(je,t)}function Y_(t){for(var e=t;;){if(e.flags&16384){var n=e.updateQueue;if(n!==null&&(n=n.stores,n!==null))for(var r=0;r<n.length;r++){var i=n[r],o=i.getSnapshot;i=i.value;try{if(!pt(o(),i))return!1}catch{return!1}}}if(n=e.child,e.subtreeFlags&16384&&n!==null)n.return=e,e=n;else{if(e===t)break;for(;e.sibling===null;){if(e.return===null||e.return===t)return!0;e=e.return}e.sibling.return=e.return,e=e.sibling}}return!0}function cn(t,e){for(e&=~yc,e&=~cl,t.suspendedLanes|=e,t.pingedLanes&=~e,t=t.expirationTimes;0<e;){var n=31-ft(e),r=1<<n;t[n]=-1,e&=~r}}function Wf(t){if(q&6)throw Error(D(327));xr();var e=ko(t,0);if(!(e&1))return be(t,he()),null;var n=Bo(t,e);if(t.tag!==0&&n===2){var r=Ga(t);r!==0&&(e=r,n=wu(t,r))}if(n===1)throw n=hs,Xn(t,0),cn(t,e),be(t,he()),n;if(n===6)throw Error(D(345));return t.finishedWork=t.current.alternate,t.finishedLanes=e,bn(t,je,Ot),be(t,he()),null}function _c(t,e){var n=q;q|=1;try{return t(e)}finally{q=n,q===0&&(Wr=he()+500,ol&&Dn())}}function ir(t){gn!==null&&gn.tag===0&&!(q&6)&&xr();var e=q;q|=1;var n=tt.transition,r=Q;try{if(tt.transition=null,Q=1,t)return t()}finally{Q=r,tt.transition=n,q=e,!(q&6)&&Dn()}}function wc(){He=Pr.current,ne(Pr)}function Xn(t,e){t.finishedWork=null,t.finishedLanes=0;var n=t.timeoutHandle;if(n!==-1&&(t.timeoutHandle=-1,A_(n)),fe!==null)for(n=fe.return;n!==null;){var r=n;switch(ec(r),r.tag){case 1:r=r.type.childContextTypes,r!=null&&No();break;case 3:Br(),ne(ze),ne(Re),uc();break;case 5:ac(r);break;case 4:Br();break;case 13:ne(se);break;case 19:ne(se);break;case 10:ic(r.type._context);break;case 22:case 23:wc()}n=n.return}if(_e=t,fe=t=In(t.current,null),Se=He=e,me=0,hs=null,yc=cl=rr=0,je=$i=null,Gn!==null){for(e=0;e<Gn.length;e++)if(n=Gn[e],r=n.interleaved,r!==null){n.interleaved=null;var i=r.next,o=n.pending;if(o!==null){var l=o.next;o.next=i,r.next=l}n.pending=r}Gn=null}return t}function Xg(t,e){do{var n=fe;try{if(rc(),uo.current=Vo,jo){for(var r=oe.memoizedState;r!==null;){var i=r.queue;i!==null&&(i.pending=null),r=r.next}jo=!1}if(nr=0,ve=ge=oe=null,Vi=!1,as=0,mc.current=null,n===null||n.return===null){me=1,hs=e,fe=null;break}e:{var o=t,l=n.return,u=n,h=e;if(e=Se,u.flags|=32768,h!==null&&typeof h=="object"&&typeof h.then=="function"){var d=h,k=u,S=k.tag;if(!(k.mode&1)&&(S===0||S===11||S===15)){var E=k.alternate;E?(k.updateQueue=E.updateQueue,k.memoizedState=E.memoizedState,k.lanes=E.lanes):(k.updateQueue=null,k.memoizedState=null)}var N=Df(l);if(N!==null){N.flags&=-257,Lf(N,l,u,o,e),N.mode&1&&Of(o,d,e),e=N,h=d;var O=e.updateQueue;if(O===null){var L=new Set;L.add(h),e.updateQueue=L}else O.add(h);break e}else{if(!(e&1)){Of(o,d,e),Ec();break e}h=Error(D(426))}}else if(ie&&u.mode&1){var z=Df(l);if(z!==null){!(z.flags&65536)&&(z.flags|=256),Lf(z,l,u,o,e),tc(Hr(h,u));break e}}o=h=Hr(h,u),me!==4&&(me=2),$i===null?$i=[o]:$i.push(o),o=l;do{switch(o.tag){case 3:o.flags|=65536,e&=-e,o.lanes|=e;var I=Dg(o,h,e);kf(o,I);break e;case 1:u=h;var _=o.type,T=o.stateNode;if(!(o.flags&128)&&(typeof _.getDerivedStateFromError=="function"||T!==null&&typeof T.componentDidCatch=="function"&&(En===null||!En.has(T)))){o.flags|=65536,e&=-e,o.lanes|=e;var R=Lg(o,u,e);kf(o,R);break e}}o=o.return}while(o!==null)}Yg(n)}catch(M){e=M,fe===n&&n!==null&&(fe=n=n.return);continue}break}while(!0)}function Jg(){var t=zo.current;return zo.current=Vo,t===null?Vo:t}function Ec(){(me===0||me===3||me===2)&&(me=4),_e===null||!(rr&268435455)&&!(cl&268435455)||cn(_e,Se)}function Bo(t,e){var n=q;q|=2;var r=Jg();(_e!==t||Se!==e)&&(Ot=null,Xn(t,e));do try{Z_();break}catch(i){Xg(t,i)}while(!0);if(rc(),q=n,zo.current=r,fe!==null)throw Error(D(261));return _e=null,Se=0,me}function Z_(){for(;fe!==null;)Qg(fe)}function e0(){for(;fe!==null&&!kv();)Qg(fe)}function Qg(t){var e=em(t.alternate,t,He);t.memoizedProps=t.pendingProps,e===null?Yg(t):fe=e,mc.current=null}function Yg(t){var e=t;do{var n=e.alternate;if(t=e.return,e.flags&32768){if(n=K_(n,e),n!==null){n.flags&=32767,fe=n;return}if(t!==null)t.flags|=32768,t.subtreeFlags=0,t.deletions=null;else{me=6,fe=null;return}}else if(n=G_(n,e,He),n!==null){fe=n;return}if(e=e.sibling,e!==null){fe=e;return}fe=e=t}while(e!==null);me===0&&(me=5)}function bn(t,e,n){var r=Q,i=tt.transition;try{tt.transition=null,Q=1,t0(t,e,n,r)}finally{tt.transition=i,Q=r}return null}function t0(t,e,n,r){do xr();while(gn!==null);if(q&6)throw Error(D(327));n=t.finishedWork;var i=t.finishedLanes;if(n===null)return null;if(t.finishedWork=null,t.finishedLanes=0,n===t.current)throw Error(D(177));t.callbackNode=null,t.callbackPriority=0;var o=n.lanes|n.childLanes;if(Mv(t,o),t===_e&&(fe=_e=null,Se=0),!(n.subtreeFlags&2064)&&!(n.flags&2064)||Ys||(Ys=!0,tm(To,function(){return xr(),null})),o=(n.flags&15990)!==0,n.subtreeFlags&15990||o){o=tt.transition,tt.transition=null;var l=Q;Q=1;var u=q;q|=4,mc.current=null,X_(t,n),Gg(n,t),E_(Ya),Co=!!Qa,Ya=Qa=null,t.current=n,J_(n),Cv(),q=u,Q=l,tt.transition=o}else t.current=n;if(Ys&&(Ys=!1,gn=t,bo=i),o=t.pendingLanes,o===0&&(En=null),Rv(n.stateNode),be(t,he()),e!==null)for(r=t.onRecoverableError,n=0;n<e.length;n++)i=e[n],r(i.value,{componentStack:i.stack,digest:i.digest});if($o)throw $o=!1,t=vu,vu=null,t;return bo&1&&t.tag!==0&&xr(),o=t.pendingLanes,o&1?t===_u?bi++:(bi=0,_u=t):bi=0,Dn(),null}function xr(){if(gn!==null){var t=Dp(bo),e=tt.transition,n=Q;try{if(tt.transition=null,Q=16>t?16:t,gn===null)var r=!1;else{if(t=gn,gn=null,bo=0,q&6)throw Error(D(331));var i=q;for(q|=4,j=t.current;j!==null;){var o=j,l=o.child;if(j.flags&16){var u=o.deletions;if(u!==null){for(var h=0;h<u.length;h++){var d=u[h];for(j=d;j!==null;){var k=j;switch(k.tag){case 0:case 11:case 15:zi(8,k,o)}var S=k.child;if(S!==null)S.return=k,j=S;else for(;j!==null;){k=j;var E=k.sibling,N=k.return;if(Bg(k),k===d){j=null;break}if(E!==null){E.return=N,j=E;break}j=N}}}var O=o.alternate;if(O!==null){var L=O.child;if(L!==null){O.child=null;do{var z=L.sibling;L.sibling=null,L=z}while(L!==null)}}j=o}}if(o.subtreeFlags&2064&&l!==null)l.return=o,j=l;else e:for(;j!==null;){if(o=j,o.flags&2048)switch(o.tag){case 0:case 11:case 15:zi(9,o,o.return)}var I=o.sibling;if(I!==null){I.return=o.return,j=I;break e}j=o.return}}var _=t.current;for(j=_;j!==null;){l=j;var T=l.child;if(l.subtreeFlags&2064&&T!==null)T.return=l,j=T;else e:for(l=_;j!==null;){if(u=j,u.flags&2048)try{switch(u.tag){case 0:case 11:case 15:ul(9,u)}}catch(M){ae(u,u.return,M)}if(u===l){j=null;break e}var R=u.sibling;if(R!==null){R.return=u.return,j=R;break e}j=u.return}}if(q=i,Dn(),kt&&typeof kt.onPostCommitFiberRoot=="function")try{kt.onPostCommitFiberRoot(tl,t)}catch{}r=!0}return r}finally{Q=n,tt.transition=e}}return!1}function Gf(t,e,n){e=Hr(n,e),e=Dg(t,e,1),t=wn(t,e,1),e=xe(),t!==null&&(ys(t,1,e),be(t,e))}function ae(t,e,n){if(t.tag===3)Gf(t,t,n);else for(;e!==null;){if(e.tag===3){Gf(e,t,n);break}else if(e.tag===1){var r=e.stateNode;if(typeof e.type.getDerivedStateFromError=="function"||typeof r.componentDidCatch=="function"&&(En===null||!En.has(r))){t=Hr(n,t),t=Lg(e,t,1),e=wn(e,t,1),t=xe(),e!==null&&(ys(e,1,t),be(e,t));break}}e=e.return}}function n0(t,e,n){var r=t.pingCache;r!==null&&r.delete(e),e=xe(),t.pingedLanes|=t.suspendedLanes&n,_e===t&&(Se&n)===n&&(me===4||me===3&&(Se&130023424)===Se&&500>he()-vc?Xn(t,0):yc|=n),be(t,e)}function Zg(t,e){e===0&&(t.mode&1?(e=bs,bs<<=1,!(bs&130023424)&&(bs=4194304)):e=1);var n=xe();t=Bt(t,e),t!==null&&(ys(t,e,n),be(t,n))}function r0(t){var e=t.memoizedState,n=0;e!==null&&(n=e.retryLane),Zg(t,n)}function i0(t,e){var n=0;switch(t.tag){case 13:var r=t.stateNode,i=t.memoizedState;i!==null&&(n=i.retryLane);break;case 19:r=t.stateNode;break;default:throw Error(D(314))}r!==null&&r.delete(e),Zg(t,n)}var em;em=function(t,e,n){if(t!==null)if(t.memoizedProps!==e.pendingProps||ze.current)Ve=!0;else{if(!(t.lanes&n)&&!(e.flags&128))return Ve=!1,W_(t,e,n);Ve=!!(t.flags&131072)}else Ve=!1,ie&&e.flags&1048576&&ig(e,Lo,e.index);switch(e.lanes=0,e.tag){case 2:var r=e.type;ho(t,e),t=e.pendingProps;var i=zr(e,Re.current);Lr(e,n),i=hc(null,e,r,t,i,n);var o=fc();return e.flags|=1,typeof i=="object"&&i!==null&&typeof i.render=="function"&&i.$$typeof===void 0?(e.tag=1,e.memoizedState=null,e.updateQueue=null,$e(r)?(o=!0,Oo(e)):o=!1,e.memoizedState=i.state!==null&&i.state!==void 0?i.state:null,oc(e),i.updater=al,e.stateNode=i,i._reactInternals=e,lu(e,r,t,n),e=cu(null,e,r,!0,o,n)):(e.tag=0,ie&&o&&Zu(e),De(null,e,i,n),e=e.child),e;case 16:r=e.elementType;e:{switch(ho(t,e),t=e.pendingProps,i=r._init,r=i(r._payload),e.type=r,i=e.tag=o0(r),t=ot(r,t),i){case 0:e=uu(null,e,r,t,n);break e;case 1:e=Uf(null,e,r,t,n);break e;case 11:e=xf(null,e,r,t,n);break e;case 14:e=Mf(null,e,r,ot(r.type,t),n);break e}throw Error(D(306,r,""))}return e;case 0:return r=e.type,i=e.pendingProps,i=e.elementType===r?i:ot(r,i),uu(t,e,r,i,n);case 1:return r=e.type,i=e.pendingProps,i=e.elementType===r?i:ot(r,i),Uf(t,e,r,i,n);case 3:e:{if(Fg(e),t===null)throw Error(D(387));r=e.pendingProps,o=e.memoizedState,i=o.element,cg(t,e),Uo(e,r,null,n);var l=e.memoizedState;if(r=l.element,o.isDehydrated)if(o={element:r,isDehydrated:!1,cache:l.cache,pendingSuspenseBoundaries:l.pendingSuspenseBoundaries,transitions:l.transitions},e.updateQueue.baseState=o,e.memoizedState=o,e.flags&256){i=Hr(Error(D(423)),e),e=Ff(t,e,r,n,i);break e}else if(r!==i){i=Hr(Error(D(424)),e),e=Ff(t,e,r,n,i);break e}else for(We=_n(e.stateNode.containerInfo.firstChild),Ge=e,ie=!0,at=null,n=ag(e,null,r,n),e.child=n;n;)n.flags=n.flags&-3|4096,n=n.sibling;else{if($r(),r===i){e=Ht(t,e,n);break e}De(t,e,r,n)}e=e.child}return e;case 5:return hg(e),t===null&&iu(e),r=e.type,i=e.pendingProps,o=t!==null?t.memoizedProps:null,l=i.children,Za(r,i)?l=null:o!==null&&Za(r,o)&&(e.flags|=32),Ug(t,e),De(t,e,l,n),e.child;case 6:return t===null&&iu(e),null;case 13:return jg(t,e,n);case 4:return lc(e,e.stateNode.containerInfo),r=e.pendingProps,t===null?e.child=br(e,null,r,n):De(t,e,r,n),e.child;case 11:return r=e.type,i=e.pendingProps,i=e.elementType===r?i:ot(r,i),xf(t,e,r,i,n);case 7:return De(t,e,e.pendingProps,n),e.child;case 8:return De(t,e,e.pendingProps.children,n),e.child;case 12:return De(t,e,e.pendingProps.children,n),e.child;case 10:e:{if(r=e.type._context,i=e.pendingProps,o=e.memoizedProps,l=i.value,Z(xo,r._currentValue),r._currentValue=l,o!==null)if(pt(o.value,l)){if(o.children===i.children&&!ze.current){e=Ht(t,e,n);break e}}else for(o=e.child,o!==null&&(o.return=e);o!==null;){var u=o.dependencies;if(u!==null){l=o.child;for(var h=u.firstContext;h!==null;){if(h.context===r){if(o.tag===1){h=zt(-1,n&-n),h.tag=2;var d=o.updateQueue;if(d!==null){d=d.shared;var k=d.pending;k===null?h.next=h:(h.next=k.next,k.next=h),d.pending=h}}o.lanes|=n,h=o.alternate,h!==null&&(h.lanes|=n),su(o.return,n,e),u.lanes|=n;break}h=h.next}}else if(o.tag===10)l=o.type===e.type?null:o.child;else if(o.tag===18){if(l=o.return,l===null)throw Error(D(341));l.lanes|=n,u=l.alternate,u!==null&&(u.lanes|=n),su(l,n,e),l=o.sibling}else l=o.child;if(l!==null)l.return=o;else for(l=o;l!==null;){if(l===e){l=null;break}if(o=l.sibling,o!==null){o.return=l.return,l=o;break}l=l.return}o=l}De(t,e,i.children,n),e=e.child}return e;case 9:return i=e.type,r=e.pendingProps.children,Lr(e,n),i=nt(i),r=r(i),e.flags|=1,De(t,e,r,n),e.child;case 14:return r=e.type,i=ot(r,e.pendingProps),i=ot(r.type,i),Mf(t,e,r,i,n);case 15:return xg(t,e,e.type,e.pendingProps,n);case 17:return r=e.type,i=e.pendingProps,i=e.elementType===r?i:ot(r,i),ho(t,e),e.tag=1,$e(r)?(t=!0,Oo(e)):t=!1,Lr(e,n),Og(e,r,i),lu(e,r,i,n),cu(null,e,r,!0,t,n);case 19:return Vg(t,e,n);case 22:return Mg(t,e,n)}throw Error(D(156,e.tag))};function tm(t,e){return Ap(t,e)}function s0(t,e,n,r){this.tag=t,this.key=n,this.sibling=this.child=this.return=this.stateNode=this.type=this.elementType=null,this.index=0,this.ref=null,this.pendingProps=e,this.dependencies=this.memoizedState=this.updateQueue=this.memoizedProps=null,this.mode=r,this.subtreeFlags=this.flags=0,this.deletions=null,this.childLanes=this.lanes=0,this.alternate=null}function et(t,e,n,r){return new s0(t,e,n,r)}function Sc(t){return t=t.prototype,!(!t||!t.isReactComponent)}function o0(t){if(typeof t=="function")return Sc(t)?1:0;if(t!=null){if(t=t.$$typeof,t===$u)return 11;if(t===bu)return 14}return 2}function In(t,e){var n=t.alternate;return n===null?(n=et(t.tag,e,t.key,t.mode),n.elementType=t.elementType,n.type=t.type,n.stateNode=t.stateNode,n.alternate=t,t.alternate=n):(n.pendingProps=e,n.type=t.type,n.flags=0,n.subtreeFlags=0,n.deletions=null),n.flags=t.flags&14680064,n.childLanes=t.childLanes,n.lanes=t.lanes,n.child=t.child,n.memoizedProps=t.memoizedProps,n.memoizedState=t.memoizedState,n.updateQueue=t.updateQueue,e=t.dependencies,n.dependencies=e===null?null:{lanes:e.lanes,firstContext:e.firstContext},n.sibling=t.sibling,n.index=t.index,n.ref=t.ref,n}function go(t,e,n,r,i,o){var l=2;if(r=t,typeof t=="function")Sc(t)&&(l=1);else if(typeof t=="string")l=5;else e:switch(t){case yr:return Jn(n.children,i,o,e);case zu:l=8,i|=8;break;case Oa:return t=et(12,n,e,i|2),t.elementType=Oa,t.lanes=o,t;case Da:return t=et(13,n,e,i),t.elementType=Da,t.lanes=o,t;case La:return t=et(19,n,e,i),t.elementType=La,t.lanes=o,t;case hp:return hl(n,i,o,e);default:if(typeof t=="object"&&t!==null)switch(t.$$typeof){case up:l=10;break e;case cp:l=9;break e;case $u:l=11;break e;case bu:l=14;break e;case ln:l=16,r=null;break e}throw Error(D(130,t==null?t:typeof t,""))}return e=et(l,n,e,i),e.elementType=t,e.type=r,e.lanes=o,e}function Jn(t,e,n,r){return t=et(7,t,r,e),t.lanes=n,t}function hl(t,e,n,r){return t=et(22,t,r,e),t.elementType=hp,t.lanes=n,t.stateNode={isHidden:!1},t}function ga(t,e,n){return t=et(6,t,null,e),t.lanes=n,t}function ma(t,e,n){return e=et(4,t.children!==null?t.children:[],t.key,e),e.lanes=n,e.stateNode={containerInfo:t.containerInfo,pendingChildren:null,implementation:t.implementation},e}function l0(t,e,n,r,i){this.tag=e,this.containerInfo=t,this.finishedWork=this.pingCache=this.current=this.pendingChildren=null,this.timeoutHandle=-1,this.callbackNode=this.pendingContext=this.context=null,this.callbackPriority=0,this.eventTimes=Jl(0),this.expirationTimes=Jl(-1),this.entangledLanes=this.finishedLanes=this.mutableReadLanes=this.expiredLanes=this.pingedLanes=this.suspendedLanes=this.pendingLanes=0,this.entanglements=Jl(0),this.identifierPrefix=r,this.onRecoverableError=i,this.mutableSourceEagerHydrationData=null}function Ic(t,e,n,r,i,o,l,u,h){return t=new l0(t,e,n,u,h),e===1?(e=1,o===!0&&(e|=8)):e=0,o=et(3,null,null,e),t.current=o,o.stateNode=t,o.memoizedState={element:r,isDehydrated:n,cache:null,transitions:null,pendingSuspenseBoundaries:null},oc(o),t}function a0(t,e,n){var r=3<arguments.length&&arguments[3]!==void 0?arguments[3]:null;return{$$typeof:mr,key:r==null?null:""+r,children:t,containerInfo:e,implementation:n}}function nm(t){if(!t)return An;t=t._reactInternals;e:{if(ur(t)!==t||t.tag!==1)throw Error(D(170));var e=t;do{switch(e.tag){case 3:e=e.stateNode.context;break e;case 1:if($e(e.type)){e=e.stateNode.__reactInternalMemoizedMergedChildContext;break e}}e=e.return}while(e!==null);throw Error(D(171))}if(t.tag===1){var n=t.type;if($e(n))return ng(t,n,e)}return e}function rm(t,e,n,r,i,o,l,u,h){return t=Ic(n,r,!0,t,i,o,l,u,h),t.context=nm(null),n=t.current,r=xe(),i=Sn(n),o=zt(r,i),o.callback=e??null,wn(n,o,i),t.current.lanes=i,ys(t,i,r),be(t,r),t}function fl(t,e,n,r){var i=e.current,o=xe(),l=Sn(i);return n=nm(n),e.context===null?e.context=n:e.pendingContext=n,e=zt(o,l),e.payload={element:t},r=r===void 0?null:r,r!==null&&(e.callback=r),t=wn(i,e,l),t!==null&&(dt(t,i,l,o),ao(t,i,l)),l}function Ho(t){if(t=t.current,!t.child)return null;switch(t.child.tag){case 5:return t.child.stateNode;default:return t.child.stateNode}}function Kf(t,e){if(t=t.memoizedState,t!==null&&t.dehydrated!==null){var n=t.retryLane;t.retryLane=n!==0&&n<e?n:e}}function Tc(t,e){Kf(t,e),(t=t.alternate)&&Kf(t,e)}function u0(){return null}var im=typeof reportError=="function"?reportError:function(t){console.error(t)};function kc(t){this._internalRoot=t}dl.prototype.render=kc.prototype.render=function(t){var e=this._internalRoot;if(e===null)throw Error(D(409));fl(t,e,null,null)};dl.prototype.unmount=kc.prototype.unmount=function(){var t=this._internalRoot;if(t!==null){this._internalRoot=null;var e=t.containerInfo;ir(function(){fl(null,t,null,null)}),e[bt]=null}};function dl(t){this._internalRoot=t}dl.prototype.unstable_scheduleHydration=function(t){if(t){var e=Mp();t={blockedOn:null,target:t,priority:e};for(var n=0;n<un.length&&e!==0&&e<un[n].priority;n++);un.splice(n,0,t),n===0&&Fp(t)}};function Cc(t){return!(!t||t.nodeType!==1&&t.nodeType!==9&&t.nodeType!==11)}function pl(t){return!(!t||t.nodeType!==1&&t.nodeType!==9&&t.nodeType!==11&&(t.nodeType!==8||t.nodeValue!==" react-mount-point-unstable "))}function qf(){}function c0(t,e,n,r,i){if(i){if(typeof r=="function"){var o=r;r=function(){var d=Ho(l);o.call(d)}}var l=rm(e,r,t,0,null,!1,!1,"",qf);return t._reactRootContainer=l,t[bt]=l.current,rs(t.nodeType===8?t.parentNode:t),ir(),l}for(;i=t.lastChild;)t.removeChild(i);if(typeof r=="function"){var u=r;r=function(){var d=Ho(h);u.call(d)}}var h=Ic(t,0,!1,null,null,!1,!1,"",qf);return t._reactRootContainer=h,t[bt]=h.current,rs(t.nodeType===8?t.parentNode:t),ir(function(){fl(e,h,n,r)}),h}function gl(t,e,n,r,i){var o=n._reactRootContainer;if(o){var l=o;if(typeof i=="function"){var u=i;i=function(){var h=Ho(l);u.call(h)}}fl(e,l,t,i)}else l=c0(n,e,t,i,r);return Ho(l)}Lp=function(t){switch(t.tag){case 3:var e=t.stateNode;if(e.current.memoizedState.isDehydrated){var n=Ni(e.pendingLanes);n!==0&&(Wu(e,n|1),be(e,he()),!(q&6)&&(Wr=he()+500,Dn()))}break;case 13:ir(function(){var r=Bt(t,1);if(r!==null){var i=xe();dt(r,t,1,i)}}),Tc(t,1)}};Gu=function(t){if(t.tag===13){var e=Bt(t,134217728);if(e!==null){var n=xe();dt(e,t,134217728,n)}Tc(t,134217728)}};xp=function(t){if(t.tag===13){var e=Sn(t),n=Bt(t,e);if(n!==null){var r=xe();dt(n,t,e,r)}Tc(t,e)}};Mp=function(){return Q};Up=function(t,e){var n=Q;try{return Q=t,e()}finally{Q=n}};Ba=function(t,e,n){switch(e){case"input":if(Ua(t,n),e=n.name,n.type==="radio"&&e!=null){for(n=t;n.parentNode;)n=n.parentNode;for(n=n.querySelectorAll("input[name="+JSON.stringify(""+e)+'][type="radio"]'),e=0;e<n.length;e++){var r=n[e];if(r!==t&&r.form===t.form){var i=sl(r);if(!i)throw Error(D(90));dp(r),Ua(r,i)}}}break;case"textarea":gp(t,n);break;case"select":e=n.value,e!=null&&Rr(t,!!n.multiple,e,!1)}};Sp=_c;Ip=ir;var h0={usingClientEntryPoint:!1,Events:[_s,Er,sl,wp,Ep,_c]},Pi={findFiberByHostInstance:Wn,bundleType:0,version:"18.3.1",rendererPackageName:"react-dom"},f0={bundleType:Pi.bundleType,version:Pi.version,rendererPackageName:Pi.rendererPackageName,rendererConfig:Pi.rendererConfig,overrideHookState:null,overrideHookStateDeletePath:null,overrideHookStateRenamePath:null,overrideProps:null,overridePropsDeletePath:null,overridePropsRenamePath:null,setErrorHandler:null,setSuspenseHandler:null,scheduleUpdate:null,currentDispatcherRef:Xt.ReactCurrentDispatcher,findHostInstanceByFiber:function(t){return t=Cp(t),t===null?null:t.stateNode},findFiberByHostInstance:Pi.findFiberByHostInstance||u0,findHostInstancesForRefresh:null,scheduleRefresh:null,scheduleRoot:null,setRefreshHandler:null,getCurrentFiber:null,reconcilerVersion:"18.3.1-next-f1338f8080-20240426"};if(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__<"u"){var Zs=__REACT_DEVTOOLS_GLOBAL_HOOK__;if(!Zs.isDisabled&&Zs.supportsFiber)try{tl=Zs.inject(f0),kt=Zs}catch{}}qe.__SECRET_INTERNALS_DO_NOT_USE_OR_YOU_WILL_BE_FIRED=h0;qe.createPortal=function(t,e){var n=2<arguments.length&&arguments[2]!==void 0?arguments[2]:null;if(!Cc(e))throw Error(D(200));return a0(t,e,null,n)};qe.createRoot=function(t,e){if(!Cc(t))throw Error(D(299));var n=!1,r="",i=im;return e!=null&&(e.unstable_strictMode===!0&&(n=!0),e.identifierPrefix!==void 0&&(r=e.identifierPrefix),e.onRecoverableError!==void 0&&(i=e.onRecoverableError)),e=Ic(t,1,!1,null,null,n,!1,r,i),t[bt]=e.current,rs(t.nodeType===8?t.parentNode:t),new kc(e)};qe.findDOMNode=function(t){if(t==null)return null;if(t.nodeType===1)return t;var e=t._reactInternals;if(e===void 0)throw typeof t.render=="function"?Error(D(188)):(t=Object.keys(t).join(","),Error(D(268,t)));return t=Cp(e),t=t===null?null:t.stateNode,t};qe.flushSync=function(t){return ir(t)};qe.hydrate=function(t,e,n){if(!pl(e))throw Error(D(200));return gl(null,t,e,!0,n)};qe.hydrateRoot=function(t,e,n){if(!Cc(t))throw Error(D(405));var r=n!=null&&n.hydratedSources||null,i=!1,o="",l=im;if(n!=null&&(n.unstable_strictMode===!0&&(i=!0),n.identifierPrefix!==void 0&&(o=n.identifierPrefix),n.onRecoverableError!==void 0&&(l=n.onRecoverableError)),e=rm(e,null,t,1,n??null,i,!1,o,l),t[bt]=e.current,rs(t),r)for(t=0;t<r.length;t++)n=r[t],i=n._getVersion,i=i(n._source),e.mutableSourceEagerHydrationData==null?e.mutableSourceEagerHydrationData=[n,i]:e.mutableSourceEagerHydrationData.push(n,i);return new dl(e)};qe.render=function(t,e,n){if(!pl(e))throw Error(D(200));return gl(null,t,e,!1,n)};qe.unmountComponentAtNode=function(t){if(!pl(t))throw Error(D(40));return t._reactRootContainer?(ir(function(){gl(null,null,t,!1,function(){t._reactRootContainer=null,t[bt]=null})}),!0):!1};qe.unstable_batchedUpdates=_c;qe.unstable_renderSubtreeIntoContainer=function(t,e,n,r){if(!pl(n))throw Error(D(200));if(t==null||t._reactInternals===void 0)throw Error(D(38));return gl(t,e,n,!1,r)};qe.version="18.3.1-next-f1338f8080-20240426";function sm(){if(!(typeof __REACT_DEVTOOLS_GLOBAL_HOOK__>"u"||typeof __REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE!="function"))try{__REACT_DEVTOOLS_GLOBAL_HOOK__.checkDCE(sm)}catch(t){console.error(t)}}sm(),sp.exports=qe;var d0=sp.exports,Xf=d0;Ra.createRoot=Xf.createRoot,Ra.hydrateRoot=Xf.hydrateRoot;const p0="modulepreload",g0=function(t){return"/"+t},Jf={},Be=function(e,n,r){let i=Promise.resolve();if(n&&n.length>0){document.getElementsByTagName("link");const l=document.querySelector("meta[property=csp-nonce]"),u=(l==null?void 0:l.nonce)||(l==null?void 0:l.getAttribute("nonce"));i=Promise.allSettled(n.map(h=>{if(h=g0(h),h in Jf)return;Jf[h]=!0;const d=h.endsWith(".css"),k=d?'[rel="stylesheet"]':"";if(document.querySelector(`link[href="${h}"]${k}`))return;const S=document.createElement("link");if(S.rel=d?"stylesheet":p0,d||(S.as="script"),S.crossOrigin="",S.href=h,u&&S.setAttribute("nonce",u),document.head.appendChild(S),d)return new Promise((E,N)=>{S.addEventListener("load",E),S.addEventListener("error",()=>N(new Error(`Unable to preload CSS for ${h}`)))})}))}function o(l){const u=new Event("vite:preloadError",{cancelable:!0});if(u.payload=l,window.dispatchEvent(u),!u.defaultPrevented)throw l}return i.then(l=>{for(const u of l||[])u.status==="rejected"&&o(u.reason);return e().catch(o)})};let m0={data:""},y0=t=>{if(typeof window=="object"){let e=(t?t.querySelector("#_goober"):window._goober)||Object.assign(document.createElement("style"),{innerHTML:" ",id:"_goober"});return e.nonce=window.__nonce__,e.parentNode||(t||document.head).appendChild(e),e.firstChild}return t||m0},v0=/(?:([\u0080-\uFFFF\w-%@]+) *:? *([^{;]+?);|([^;}{]*?) *{)|(}\s*)/g,_0=/\/\*[^]*?\*\/|  +/g,Qf=/\n+/g,hn=(t,e)=>{let n="",r="",i="";for(let o in t){let l=t[o];o[0]=="@"?o[1]=="i"?n=o+" "+l+";":r+=o[1]=="f"?hn(l,o):o+"{"+hn(l,o[1]=="k"?"":e)+"}":typeof l=="object"?r+=hn(l,e?e.replace(/([^,])+/g,u=>o.replace(/([^,]*:\S+\([^)]*\))|([^,])+/g,h=>/&/.test(h)?h.replace(/&/g,u):u?u+" "+h:h)):o):l!=null&&(o=/^--/.test(o)?o:o.replace(/[A-Z]/g,"-$&").toLowerCase(),i+=hn.p?hn.p(o,l):o+":"+l+";")}return n+(e&&i?e+"{"+i+"}":i)+r},Nt={},om=t=>{if(typeof t=="object"){let e="";for(let n in t)e+=n+om(t[n]);return e}return t},w0=(t,e,n,r,i)=>{let o=om(t),l=Nt[o]||(Nt[o]=(h=>{let d=0,k=11;for(;d<h.length;)k=101*k+h.charCodeAt(d++)>>>0;return"go"+k})(o));if(!Nt[l]){let h=o!==t?t:(d=>{let k,S,E=[{}];for(;k=v0.exec(d.replace(_0,""));)k[4]?E.shift():k[3]?(S=k[3].replace(Qf," ").trim(),E.unshift(E[0][S]=E[0][S]||{})):E[0][k[1]]=k[2].replace(Qf," ").trim();return E[0]})(t);Nt[l]=hn(i?{["@keyframes "+l]:h}:h,n?"":"."+l)}let u=n&&Nt.g?Nt.g:null;return n&&(Nt.g=Nt[l]),((h,d,k,S)=>{S?d.data=d.data.replace(S,h):d.data.indexOf(h)===-1&&(d.data=k?h+d.data:d.data+h)})(Nt[l],e,r,u),l},E0=(t,e,n)=>t.reduce((r,i,o)=>{let l=e[o];if(l&&l.call){let u=l(n),h=u&&u.props&&u.props.className||/^go/.test(u)&&u;l=h?"."+h:u&&typeof u=="object"?u.props?"":hn(u,""):u===!1?"":u}return r+i+(l??"")},"");function ml(t){let e=this||{},n=t.call?t(e.p):t;return w0(n.unshift?n.raw?E0(n,[].slice.call(arguments,1),e.p):n.reduce((r,i)=>Object.assign(r,i&&i.call?i(e.p):i),{}):n,y0(e.target),e.g,e.o,e.k)}let lm,Su,Iu;ml.bind({g:1});let Wt=ml.bind({k:1});function S0(t,e,n,r){hn.p=e,lm=t,Su=n,Iu=r}function Ln(t,e){let n=this||{};return function(){let r=arguments;function i(o,l){let u=Object.assign({},o),h=u.className||i.className;n.p=Object.assign({theme:Su&&Su()},u),n.o=/ *go\d+/.test(h),u.className=ml.apply(n,r)+(h?" "+h:"");let d=t;return t[0]&&(d=u.as||t,delete u.as),Iu&&d[0]&&Iu(u),lm(d,u)}return i}}var I0=t=>typeof t=="function",T0=(t,e)=>I0(t)?t(e):t,k0=(()=>{let t;return()=>{if(t===void 0&&typeof window<"u"){let e=matchMedia("(prefers-reduced-motion: reduce)");t=!e||e.matches}return t}})(),C0=Wt`
from {
  transform: scale(0) rotate(45deg);
	opacity: 0;
}
to {
 transform: scale(1) rotate(45deg);
  opacity: 1;
}`,P0=Wt`
from {
  transform: scale(0);
  opacity: 0;
}
to {
  transform: scale(1);
  opacity: 1;
}`,A0=Wt`
from {
  transform: scale(0) rotate(90deg);
	opacity: 0;
}
to {
  transform: scale(1) rotate(90deg);
	opacity: 1;
}`,R0=Ln("div")`
  width: 20px;
  opacity: 0;
  height: 20px;
  border-radius: 10px;
  background: ${t=>t.primary||"#ff4b4b"};
  position: relative;
  transform: rotate(45deg);

  animation: ${C0} 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)
    forwards;
  animation-delay: 100ms;

  &:after,
  &:before {
    content: '';
    animation: ${P0} 0.15s ease-out forwards;
    animation-delay: 150ms;
    position: absolute;
    border-radius: 3px;
    opacity: 0;
    background: ${t=>t.secondary||"#fff"};
    bottom: 9px;
    left: 4px;
    height: 2px;
    width: 12px;
  }

  &:before {
    animation: ${A0} 0.15s ease-out forwards;
    animation-delay: 180ms;
    transform: rotate(90deg);
  }
`,N0=Wt`
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
`,O0=Ln("div")`
  width: 12px;
  height: 12px;
  box-sizing: border-box;
  border: 2px solid;
  border-radius: 100%;
  border-color: ${t=>t.secondary||"#e0e0e0"};
  border-right-color: ${t=>t.primary||"#616161"};
  animation: ${N0} 1s linear infinite;
`,D0=Wt`
from {
  transform: scale(0) rotate(45deg);
	opacity: 0;
}
to {
  transform: scale(1) rotate(45deg);
	opacity: 1;
}`,L0=Wt`
0% {
	height: 0;
	width: 0;
	opacity: 0;
}
40% {
  height: 0;
	width: 6px;
	opacity: 1;
}
100% {
  opacity: 1;
  height: 10px;
}`,x0=Ln("div")`
  width: 20px;
  opacity: 0;
  height: 20px;
  border-radius: 10px;
  background: ${t=>t.primary||"#61d345"};
  position: relative;
  transform: rotate(45deg);

  animation: ${D0} 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275)
    forwards;
  animation-delay: 100ms;
  &:after {
    content: '';
    box-sizing: border-box;
    animation: ${L0} 0.2s ease-out forwards;
    opacity: 0;
    animation-delay: 200ms;
    position: absolute;
    border-right: 2px solid;
    border-bottom: 2px solid;
    border-color: ${t=>t.secondary||"#fff"};
    bottom: 6px;
    left: 6px;
    height: 10px;
    width: 6px;
  }
`,M0=Ln("div")`
  position: absolute;
`,U0=Ln("div")`
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  min-width: 20px;
  min-height: 20px;
`,F0=Wt`
from {
  transform: scale(0.6);
  opacity: 0.4;
}
to {
  transform: scale(1);
  opacity: 1;
}`,j0=Ln("div")`
  position: relative;
  transform: scale(0.6);
  opacity: 0.4;
  min-width: 20px;
  animation: ${F0} 0.3s 0.12s cubic-bezier(0.175, 0.885, 0.32, 1.275)
    forwards;
`,V0=({toast:t})=>{let{icon:e,type:n,iconTheme:r}=t;return e!==void 0?typeof e=="string"?X.createElement(j0,null,e):e:n==="blank"?null:X.createElement(U0,null,X.createElement(O0,{...r}),n!=="loading"&&X.createElement(M0,null,n==="error"?X.createElement(R0,{...r}):X.createElement(x0,{...r})))},z0=t=>`
0% {transform: translate3d(0,${t*-200}%,0) scale(.6); opacity:.5;}
100% {transform: translate3d(0,0,0) scale(1); opacity:1;}
`,$0=t=>`
0% {transform: translate3d(0,0,-1px) scale(1); opacity:1;}
100% {transform: translate3d(0,${t*-150}%,-1px) scale(.6); opacity:0;}
`,b0="0%{opacity:0;} 100%{opacity:1;}",B0="0%{opacity:1;} 100%{opacity:0;}",H0=Ln("div")`
  display: flex;
  align-items: center;
  background: #fff;
  color: #363636;
  line-height: 1.3;
  will-change: transform;
  box-shadow: 0 3px 10px rgba(0, 0, 0, 0.1), 0 3px 3px rgba(0, 0, 0, 0.05);
  max-width: 350px;
  pointer-events: auto;
  padding: 8px 10px;
  border-radius: 8px;
`,W0=Ln("div")`
  display: flex;
  justify-content: center;
  margin: 4px 10px;
  color: inherit;
  flex: 1 1 auto;
  white-space: pre-line;
`,G0=(t,e)=>{let n=t.includes("top")?1:-1,[r,i]=k0()?[b0,B0]:[z0(n),$0(n)];return{animation:e?`${Wt(r)} 0.35s cubic-bezier(.21,1.02,.73,1) forwards`:`${Wt(i)} 0.4s forwards cubic-bezier(.06,.71,.55,1)`}};X.memo(({toast:t,position:e,style:n,children:r})=>{let i=t.height?G0(t.position||e||"top-center",t.visible):{opacity:0},o=X.createElement(V0,{toast:t}),l=X.createElement(W0,{...t.ariaProps},T0(t.message,t));return X.createElement(H0,{className:t.className,style:{...i,...n,...t.style}},typeof r=="function"?r({icon:o,message:l}):X.createElement(X.Fragment,null,o,l))});S0(X.createElement);ml`
  z-index: 9999;
  > * {
    pointer-events: auto;
  }
`;X.lazy(()=>Be(()=>import("./index-CLDelqcO.js"),[]).then(t=>({default:t.AreaChart})));X.lazy(()=>Be(()=>import("./index-CLDelqcO.js"),[]).then(t=>({default:t.Area})));X.lazy(()=>Be(()=>import("./index-CLDelqcO.js"),[]).then(t=>({default:t.XAxis})));X.lazy(()=>Be(()=>import("./index-CLDelqcO.js"),[]).then(t=>({default:t.YAxis})));X.lazy(()=>Be(()=>import("./index-CLDelqcO.js"),[]).then(t=>({default:t.CartesianGrid})));X.lazy(()=>Be(()=>import("./index-CLDelqcO.js"),[]).then(t=>({default:t.Tooltip})));X.lazy(()=>Be(()=>import("./index-CLDelqcO.js"),[]).then(t=>({default:t.ResponsiveContainer})));const K0=()=>{};var Yf={};/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const am=function(t){const e=[];let n=0;for(let r=0;r<t.length;r++){let i=t.charCodeAt(r);i<128?e[n++]=i:i<2048?(e[n++]=i>>6|192,e[n++]=i&63|128):(i&64512)===55296&&r+1<t.length&&(t.charCodeAt(r+1)&64512)===56320?(i=65536+((i&1023)<<10)+(t.charCodeAt(++r)&1023),e[n++]=i>>18|240,e[n++]=i>>12&63|128,e[n++]=i>>6&63|128,e[n++]=i&63|128):(e[n++]=i>>12|224,e[n++]=i>>6&63|128,e[n++]=i&63|128)}return e},q0=function(t){const e=[];let n=0,r=0;for(;n<t.length;){const i=t[n++];if(i<128)e[r++]=String.fromCharCode(i);else if(i>191&&i<224){const o=t[n++];e[r++]=String.fromCharCode((i&31)<<6|o&63)}else if(i>239&&i<365){const o=t[n++],l=t[n++],u=t[n++],h=((i&7)<<18|(o&63)<<12|(l&63)<<6|u&63)-65536;e[r++]=String.fromCharCode(55296+(h>>10)),e[r++]=String.fromCharCode(56320+(h&1023))}else{const o=t[n++],l=t[n++];e[r++]=String.fromCharCode((i&15)<<12|(o&63)<<6|l&63)}}return e.join("")},um={byteToCharMap_:null,charToByteMap_:null,byteToCharMapWebSafe_:null,charToByteMapWebSafe_:null,ENCODED_VALS_BASE:"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",get ENCODED_VALS(){return this.ENCODED_VALS_BASE+"+/="},get ENCODED_VALS_WEBSAFE(){return this.ENCODED_VALS_BASE+"-_."},HAS_NATIVE_SUPPORT:typeof atob=="function",encodeByteArray(t,e){if(!Array.isArray(t))throw Error("encodeByteArray takes an array as a parameter");this.init_();const n=e?this.byteToCharMapWebSafe_:this.byteToCharMap_,r=[];for(let i=0;i<t.length;i+=3){const o=t[i],l=i+1<t.length,u=l?t[i+1]:0,h=i+2<t.length,d=h?t[i+2]:0,k=o>>2,S=(o&3)<<4|u>>4;let E=(u&15)<<2|d>>6,N=d&63;h||(N=64,l||(E=64)),r.push(n[k],n[S],n[E],n[N])}return r.join("")},encodeString(t,e){return this.HAS_NATIVE_SUPPORT&&!e?btoa(t):this.encodeByteArray(am(t),e)},decodeString(t,e){return this.HAS_NATIVE_SUPPORT&&!e?atob(t):q0(this.decodeStringToByteArray(t,e))},decodeStringToByteArray(t,e){this.init_();const n=e?this.charToByteMapWebSafe_:this.charToByteMap_,r=[];for(let i=0;i<t.length;){const o=n[t.charAt(i++)],u=i<t.length?n[t.charAt(i)]:0;++i;const d=i<t.length?n[t.charAt(i)]:64;++i;const S=i<t.length?n[t.charAt(i)]:64;if(++i,o==null||u==null||d==null||S==null)throw new X0;const E=o<<2|u>>4;if(r.push(E),d!==64){const N=u<<4&240|d>>2;if(r.push(N),S!==64){const O=d<<6&192|S;r.push(O)}}}return r},init_(){if(!this.byteToCharMap_){this.byteToCharMap_={},this.charToByteMap_={},this.byteToCharMapWebSafe_={},this.charToByteMapWebSafe_={};for(let t=0;t<this.ENCODED_VALS.length;t++)this.byteToCharMap_[t]=this.ENCODED_VALS.charAt(t),this.charToByteMap_[this.byteToCharMap_[t]]=t,this.byteToCharMapWebSafe_[t]=this.ENCODED_VALS_WEBSAFE.charAt(t),this.charToByteMapWebSafe_[this.byteToCharMapWebSafe_[t]]=t,t>=this.ENCODED_VALS_BASE.length&&(this.charToByteMap_[this.ENCODED_VALS_WEBSAFE.charAt(t)]=t,this.charToByteMapWebSafe_[this.ENCODED_VALS.charAt(t)]=t)}}};class X0 extends Error{constructor(){super(...arguments),this.name="DecodeBase64StringError"}}const J0=function(t){const e=am(t);return um.encodeByteArray(e,!0)},Wo=function(t){return J0(t).replace(/\./g,"")},cm=function(t){try{return um.decodeString(t,!0)}catch(e){console.error("base64Decode failed: ",e)}return null};/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function Q0(){if(typeof self<"u")return self;if(typeof window<"u")return window;if(typeof global<"u")return global;throw new Error("Unable to locate global object.")}/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Y0=()=>Q0().__FIREBASE_DEFAULTS__,Z0=()=>{if(typeof process>"u"||typeof Yf>"u")return;const t=Yf.__FIREBASE_DEFAULTS__;if(t)return JSON.parse(t)},e1=()=>{if(typeof document>"u")return;let t;try{t=document.cookie.match(/__FIREBASE_DEFAULTS__=([^;]+)/)}catch{return}const e=t&&cm(t[1]);return e&&JSON.parse(e)},Pc=()=>{try{return K0()||Y0()||Z0()||e1()}catch(t){console.info(`Unable to get __FIREBASE_DEFAULTS__ due to: ${t}`);return}},hm=t=>{var e,n;return(n=(e=Pc())==null?void 0:e.emulatorHosts)==null?void 0:n[t]},t1=t=>{const e=hm(t);if(!e)return;const n=e.lastIndexOf(":");if(n<=0||n+1===e.length)throw new Error(`Invalid host ${e} with no separate hostname and port!`);const r=parseInt(e.substring(n+1),10);return e[0]==="["?[e.substring(1,n-1),r]:[e.substring(0,n),r]},fm=()=>{var t;return(t=Pc())==null?void 0:t.config},dm=t=>{var e;return(e=Pc())==null?void 0:e[`_${t}`]};/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class n1{constructor(){this.reject=()=>{},this.resolve=()=>{},this.promise=new Promise((e,n)=>{this.resolve=e,this.reject=n})}wrapCallback(e){return(n,r)=>{n?this.reject(n):this.resolve(r),typeof e=="function"&&(this.promise.catch(()=>{}),e.length===1?e(n):e(n,r))}}}/**
 * @license
 * Copyright 2025 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function Es(t){try{return(t.startsWith("http://")||t.startsWith("https://")?new URL(t).hostname:t).endsWith(".cloudworkstations.dev")}catch{return!1}}async function pm(t){return(await fetch(t,{credentials:"include"})).ok}/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function r1(t,e){if(t.uid)throw new Error('The "uid" field is no longer supported by mockUserToken. Please use "sub" instead for Firebase Auth User ID.');const n={alg:"none",type:"JWT"},r=e||"demo-project",i=t.iat||0,o=t.sub||t.user_id;if(!o)throw new Error("mockUserToken must contain 'sub' or 'user_id' field!");const l={iss:`https://securetoken.google.com/${r}`,aud:r,iat:i,exp:i+3600,auth_time:i,sub:o,user_id:o,firebase:{sign_in_provider:"custom",identities:{}},...t};return[Wo(JSON.stringify(n)),Wo(JSON.stringify(l)),""].join(".")}const Bi={};function i1(){const t={prod:[],emulator:[]};for(const e of Object.keys(Bi))Bi[e]?t.emulator.push(e):t.prod.push(e);return t}function s1(t){let e=document.getElementById(t),n=!1;return e||(e=document.createElement("div"),e.setAttribute("id",t),n=!0),{created:n,element:e}}let Zf=!1;function gm(t,e){if(typeof window>"u"||typeof document>"u"||!Es(window.location.host)||Bi[t]===e||Bi[t]||Zf)return;Bi[t]=e;function n(E){return`__firebase__banner__${E}`}const r="__firebase__banner",o=i1().prod.length>0;function l(){const E=document.getElementById(r);E&&E.remove()}function u(E){E.style.display="flex",E.style.background="#7faaf0",E.style.position="fixed",E.style.bottom="5px",E.style.left="5px",E.style.padding=".5em",E.style.borderRadius="5px",E.style.alignItems="center"}function h(E,N){E.setAttribute("width","24"),E.setAttribute("id",N),E.setAttribute("height","24"),E.setAttribute("viewBox","0 0 24 24"),E.setAttribute("fill","none"),E.style.marginLeft="-6px"}function d(){const E=document.createElement("span");return E.style.cursor="pointer",E.style.marginLeft="16px",E.style.fontSize="24px",E.innerHTML=" &times;",E.onclick=()=>{Zf=!0,l()},E}function k(E,N){E.setAttribute("id",N),E.innerText="Learn more",E.href="https://firebase.google.com/docs/studio/preview-apps#preview-backend",E.setAttribute("target","__blank"),E.style.paddingLeft="5px",E.style.textDecoration="underline"}function S(){const E=s1(r),N=n("text"),O=document.getElementById(N)||document.createElement("span"),L=n("learnmore"),z=document.getElementById(L)||document.createElement("a"),I=n("preprendIcon"),_=document.getElementById(I)||document.createElementNS("http://www.w3.org/2000/svg","svg");if(E.created){const T=E.element;u(T),k(z,L);const R=d();h(_,I),T.append(_,O,z,R),document.body.appendChild(T)}o?(O.innerText="Preview backend disconnected.",_.innerHTML=`<g clip-path="url(#clip0_6013_33858)">
<path d="M4.8 17.6L12 5.6L19.2 17.6H4.8ZM6.91667 16.4H17.0833L12 7.93333L6.91667 16.4ZM12 15.6C12.1667 15.6 12.3056 15.5444 12.4167 15.4333C12.5389 15.3111 12.6 15.1667 12.6 15C12.6 14.8333 12.5389 14.6944 12.4167 14.5833C12.3056 14.4611 12.1667 14.4 12 14.4C11.8333 14.4 11.6889 14.4611 11.5667 14.5833C11.4556 14.6944 11.4 14.8333 11.4 15C11.4 15.1667 11.4556 15.3111 11.5667 15.4333C11.6889 15.5444 11.8333 15.6 12 15.6ZM11.4 13.6H12.6V10.4H11.4V13.6Z" fill="#212121"/>
</g>
<defs>
<clipPath id="clip0_6013_33858">
<rect width="24" height="24" fill="white"/>
</clipPath>
</defs>`):(_.innerHTML=`<g clip-path="url(#clip0_6083_34804)">
<path d="M11.4 15.2H12.6V11.2H11.4V15.2ZM12 10C12.1667 10 12.3056 9.94444 12.4167 9.83333C12.5389 9.71111 12.6 9.56667 12.6 9.4C12.6 9.23333 12.5389 9.09444 12.4167 8.98333C12.3056 8.86111 12.1667 8.8 12 8.8C11.8333 8.8 11.6889 8.86111 11.5667 8.98333C11.4556 9.09444 11.4 9.23333 11.4 9.4C11.4 9.56667 11.4556 9.71111 11.5667 9.83333C11.6889 9.94444 11.8333 10 12 10ZM12 18.4C11.1222 18.4 10.2944 18.2333 9.51667 17.9C8.73889 17.5667 8.05556 17.1111 7.46667 16.5333C6.88889 15.9444 6.43333 15.2611 6.1 14.4833C5.76667 13.7056 5.6 12.8778 5.6 12C5.6 11.1111 5.76667 10.2833 6.1 9.51667C6.43333 8.73889 6.88889 8.06111 7.46667 7.48333C8.05556 6.89444 8.73889 6.43333 9.51667 6.1C10.2944 5.76667 11.1222 5.6 12 5.6C12.8889 5.6 13.7167 5.76667 14.4833 6.1C15.2611 6.43333 15.9389 6.89444 16.5167 7.48333C17.1056 8.06111 17.5667 8.73889 17.9 9.51667C18.2333 10.2833 18.4 11.1111 18.4 12C18.4 12.8778 18.2333 13.7056 17.9 14.4833C17.5667 15.2611 17.1056 15.9444 16.5167 16.5333C15.9389 17.1111 15.2611 17.5667 14.4833 17.9C13.7167 18.2333 12.8889 18.4 12 18.4ZM12 17.2C13.4444 17.2 14.6722 16.6944 15.6833 15.6833C16.6944 14.6722 17.2 13.4444 17.2 12C17.2 10.5556 16.6944 9.32778 15.6833 8.31667C14.6722 7.30555 13.4444 6.8 12 6.8C10.5556 6.8 9.32778 7.30555 8.31667 8.31667C7.30556 9.32778 6.8 10.5556 6.8 12C6.8 13.4444 7.30556 14.6722 8.31667 15.6833C9.32778 16.6944 10.5556 17.2 12 17.2Z" fill="#212121"/>
</g>
<defs>
<clipPath id="clip0_6083_34804">
<rect width="24" height="24" fill="white"/>
</clipPath>
</defs>`,O.innerText="Preview backend running in this workspace."),O.setAttribute("id",N)}document.readyState==="loading"?window.addEventListener("DOMContentLoaded",S):S()}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function Me(){return typeof navigator<"u"&&typeof navigator.userAgent=="string"?navigator.userAgent:""}function o1(){return typeof window<"u"&&!!(window.cordova||window.phonegap||window.PhoneGap)&&/ios|iphone|ipod|ipad|android|blackberry|iemobile/i.test(Me())}function l1(){return typeof navigator<"u"&&navigator.userAgent==="Cloudflare-Workers"}function a1(){const t=typeof chrome=="object"?chrome.runtime:typeof browser=="object"?browser.runtime:void 0;return typeof t=="object"&&t.id!==void 0}function u1(){return typeof navigator=="object"&&navigator.product==="ReactNative"}function c1(){const t=Me();return t.indexOf("MSIE ")>=0||t.indexOf("Trident/")>=0}function h1(){try{return typeof indexedDB=="object"}catch{return!1}}function f1(){return new Promise((t,e)=>{try{let n=!0;const r="validate-browser-context-for-indexeddb-analytics-module",i=self.indexedDB.open(r);i.onsuccess=()=>{i.result.close(),n||self.indexedDB.deleteDatabase(r),t(!0)},i.onupgradeneeded=()=>{n=!1},i.onerror=()=>{var o;e(((o=i.error)==null?void 0:o.message)||"")}}catch(n){e(n)}})}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const d1="FirebaseError";class Jt extends Error{constructor(e,n,r){super(n),this.code=e,this.customData=r,this.name=d1,Object.setPrototypeOf(this,Jt.prototype),Error.captureStackTrace&&Error.captureStackTrace(this,Ss.prototype.create)}}class Ss{constructor(e,n,r){this.service=e,this.serviceName=n,this.errors=r}create(e,...n){const r=n[0]||{},i=`${this.service}/${e}`,o=this.errors[e],l=o?p1(o,r):"Error",u=`${this.serviceName}: ${l} (${i}).`;return new Jt(i,u,r)}}function p1(t,e){return t.replace(g1,(n,r)=>{const i=e[r];return i!=null?String(i):`<${r}?>`})}const g1=/\{\$([^}]+)}/g;function m1(t){for(const e in t)if(Object.prototype.hasOwnProperty.call(t,e))return!1;return!0}function sr(t,e){if(t===e)return!0;const n=Object.keys(t),r=Object.keys(e);for(const i of n){if(!r.includes(i))return!1;const o=t[i],l=e[i];if(ed(o)&&ed(l)){if(!sr(o,l))return!1}else if(o!==l)return!1}for(const i of r)if(!n.includes(i))return!1;return!0}function ed(t){return t!==null&&typeof t=="object"}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function Is(t){const e=[];for(const[n,r]of Object.entries(t))Array.isArray(r)?r.forEach(i=>{e.push(encodeURIComponent(n)+"="+encodeURIComponent(i))}):e.push(encodeURIComponent(n)+"="+encodeURIComponent(r));return e.length?"&"+e.join("&"):""}function Di(t){const e={};return t.replace(/^\?/,"").split("&").forEach(r=>{if(r){const[i,o]=r.split("=");e[decodeURIComponent(i)]=decodeURIComponent(o)}}),e}function Li(t){const e=t.indexOf("?");if(!e)return"";const n=t.indexOf("#",e);return t.substring(e,n>0?n:void 0)}function y1(t,e){const n=new v1(t,e);return n.subscribe.bind(n)}class v1{constructor(e,n){this.observers=[],this.unsubscribes=[],this.observerCount=0,this.task=Promise.resolve(),this.finalized=!1,this.onNoObservers=n,this.task.then(()=>{e(this)}).catch(r=>{this.error(r)})}next(e){this.forEachObserver(n=>{n.next(e)})}error(e){this.forEachObserver(n=>{n.error(e)}),this.close(e)}complete(){this.forEachObserver(e=>{e.complete()}),this.close()}subscribe(e,n,r){let i;if(e===void 0&&n===void 0&&r===void 0)throw new Error("Missing Observer.");_1(e,["next","error","complete"])?i=e:i={next:e,error:n,complete:r},i.next===void 0&&(i.next=ya),i.error===void 0&&(i.error=ya),i.complete===void 0&&(i.complete=ya);const o=this.unsubscribeOne.bind(this,this.observers.length);return this.finalized&&this.task.then(()=>{try{this.finalError?i.error(this.finalError):i.complete()}catch{}}),this.observers.push(i),o}unsubscribeOne(e){this.observers===void 0||this.observers[e]===void 0||(delete this.observers[e],this.observerCount-=1,this.observerCount===0&&this.onNoObservers!==void 0&&this.onNoObservers(this))}forEachObserver(e){if(!this.finalized)for(let n=0;n<this.observers.length;n++)this.sendOne(n,e)}sendOne(e,n){this.task.then(()=>{if(this.observers!==void 0&&this.observers[e]!==void 0)try{n(this.observers[e])}catch(r){typeof console<"u"&&console.error&&console.error(r)}})}close(e){this.finalized||(this.finalized=!0,e!==void 0&&(this.finalError=e),this.task.then(()=>{this.observers=void 0,this.onNoObservers=void 0}))}}function _1(t,e){if(typeof t!="object"||t===null)return!1;for(const n of e)if(n in t&&typeof t[n]=="function")return!0;return!1}function ya(){}/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function Yr(t){return t&&t._delegate?t._delegate:t}class or{constructor(e,n,r){this.name=e,this.instanceFactory=n,this.type=r,this.multipleInstances=!1,this.serviceProps={},this.instantiationMode="LAZY",this.onInstanceCreated=null}setInstantiationMode(e){return this.instantiationMode=e,this}setMultipleInstances(e){return this.multipleInstances=e,this}setServiceProps(e){return this.serviceProps=e,this}setInstanceCreatedCallback(e){return this.onInstanceCreated=e,this}}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Bn="[DEFAULT]";/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class w1{constructor(e,n){this.name=e,this.container=n,this.component=null,this.instances=new Map,this.instancesDeferred=new Map,this.instancesOptions=new Map,this.onInitCallbacks=new Map}get(e){const n=this.normalizeInstanceIdentifier(e);if(!this.instancesDeferred.has(n)){const r=new n1;if(this.instancesDeferred.set(n,r),this.isInitialized(n)||this.shouldAutoInitialize())try{const i=this.getOrInitializeService({instanceIdentifier:n});i&&r.resolve(i)}catch{}}return this.instancesDeferred.get(n).promise}getImmediate(e){const n=this.normalizeInstanceIdentifier(e==null?void 0:e.identifier),r=(e==null?void 0:e.optional)??!1;if(this.isInitialized(n)||this.shouldAutoInitialize())try{return this.getOrInitializeService({instanceIdentifier:n})}catch(i){if(r)return null;throw i}else{if(r)return null;throw Error(`Service ${this.name} is not available`)}}getComponent(){return this.component}setComponent(e){if(e.name!==this.name)throw Error(`Mismatching Component ${e.name} for Provider ${this.name}.`);if(this.component)throw Error(`Component for ${this.name} has already been provided`);if(this.component=e,!!this.shouldAutoInitialize()){if(S1(e))try{this.getOrInitializeService({instanceIdentifier:Bn})}catch{}for(const[n,r]of this.instancesDeferred.entries()){const i=this.normalizeInstanceIdentifier(n);try{const o=this.getOrInitializeService({instanceIdentifier:i});r.resolve(o)}catch{}}}}clearInstance(e=Bn){this.instancesDeferred.delete(e),this.instancesOptions.delete(e),this.instances.delete(e)}async delete(){const e=Array.from(this.instances.values());await Promise.all([...e.filter(n=>"INTERNAL"in n).map(n=>n.INTERNAL.delete()),...e.filter(n=>"_delete"in n).map(n=>n._delete())])}isComponentSet(){return this.component!=null}isInitialized(e=Bn){return this.instances.has(e)}getOptions(e=Bn){return this.instancesOptions.get(e)||{}}initialize(e={}){const{options:n={}}=e,r=this.normalizeInstanceIdentifier(e.instanceIdentifier);if(this.isInitialized(r))throw Error(`${this.name}(${r}) has already been initialized`);if(!this.isComponentSet())throw Error(`Component ${this.name} has not been registered yet`);const i=this.getOrInitializeService({instanceIdentifier:r,options:n});for(const[o,l]of this.instancesDeferred.entries()){const u=this.normalizeInstanceIdentifier(o);r===u&&l.resolve(i)}return i}onInit(e,n){const r=this.normalizeInstanceIdentifier(n),i=this.onInitCallbacks.get(r)??new Set;i.add(e),this.onInitCallbacks.set(r,i);const o=this.instances.get(r);return o&&e(o,r),()=>{i.delete(e)}}invokeOnInitCallbacks(e,n){const r=this.onInitCallbacks.get(n);if(r)for(const i of r)try{i(e,n)}catch{}}getOrInitializeService({instanceIdentifier:e,options:n={}}){let r=this.instances.get(e);if(!r&&this.component&&(r=this.component.instanceFactory(this.container,{instanceIdentifier:E1(e),options:n}),this.instances.set(e,r),this.instancesOptions.set(e,n),this.invokeOnInitCallbacks(r,e),this.component.onInstanceCreated))try{this.component.onInstanceCreated(this.container,e,r)}catch{}return r||null}normalizeInstanceIdentifier(e=Bn){return this.component?this.component.multipleInstances?e:Bn:e}shouldAutoInitialize(){return!!this.component&&this.component.instantiationMode!=="EXPLICIT"}}function E1(t){return t===Bn?void 0:t}function S1(t){return t.instantiationMode==="EAGER"}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class I1{constructor(e){this.name=e,this.providers=new Map}addComponent(e){const n=this.getProvider(e.name);if(n.isComponentSet())throw new Error(`Component ${e.name} has already been registered with ${this.name}`);n.setComponent(e)}addOrOverwriteComponent(e){this.getProvider(e.name).isComponentSet()&&this.providers.delete(e.name),this.addComponent(e)}getProvider(e){if(this.providers.has(e))return this.providers.get(e);const n=new w1(e,this);return this.providers.set(e,n),n}getProviders(){return Array.from(this.providers.values())}}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var J;(function(t){t[t.DEBUG=0]="DEBUG",t[t.VERBOSE=1]="VERBOSE",t[t.INFO=2]="INFO",t[t.WARN=3]="WARN",t[t.ERROR=4]="ERROR",t[t.SILENT=5]="SILENT"})(J||(J={}));const T1={debug:J.DEBUG,verbose:J.VERBOSE,info:J.INFO,warn:J.WARN,error:J.ERROR,silent:J.SILENT},k1=J.INFO,C1={[J.DEBUG]:"log",[J.VERBOSE]:"log",[J.INFO]:"info",[J.WARN]:"warn",[J.ERROR]:"error"},P1=(t,e,...n)=>{if(e<t.logLevel)return;const r=new Date().toISOString(),i=C1[e];if(i)console[i](`[${r}]  ${t.name}:`,...n);else throw new Error(`Attempted to log a message with an invalid logType (value: ${e})`)};class Ac{constructor(e){this.name=e,this._logLevel=k1,this._logHandler=P1,this._userLogHandler=null}get logLevel(){return this._logLevel}set logLevel(e){if(!(e in J))throw new TypeError(`Invalid value "${e}" assigned to \`logLevel\``);this._logLevel=e}setLogLevel(e){this._logLevel=typeof e=="string"?T1[e]:e}get logHandler(){return this._logHandler}set logHandler(e){if(typeof e!="function")throw new TypeError("Value assigned to `logHandler` must be a function");this._logHandler=e}get userLogHandler(){return this._userLogHandler}set userLogHandler(e){this._userLogHandler=e}debug(...e){this._userLogHandler&&this._userLogHandler(this,J.DEBUG,...e),this._logHandler(this,J.DEBUG,...e)}log(...e){this._userLogHandler&&this._userLogHandler(this,J.VERBOSE,...e),this._logHandler(this,J.VERBOSE,...e)}info(...e){this._userLogHandler&&this._userLogHandler(this,J.INFO,...e),this._logHandler(this,J.INFO,...e)}warn(...e){this._userLogHandler&&this._userLogHandler(this,J.WARN,...e),this._logHandler(this,J.WARN,...e)}error(...e){this._userLogHandler&&this._userLogHandler(this,J.ERROR,...e),this._logHandler(this,J.ERROR,...e)}}const A1=(t,e)=>e.some(n=>t instanceof n);let td,nd;function R1(){return td||(td=[IDBDatabase,IDBObjectStore,IDBIndex,IDBCursor,IDBTransaction])}function N1(){return nd||(nd=[IDBCursor.prototype.advance,IDBCursor.prototype.continue,IDBCursor.prototype.continuePrimaryKey])}const mm=new WeakMap,Tu=new WeakMap,ym=new WeakMap,va=new WeakMap,Rc=new WeakMap;function O1(t){const e=new Promise((n,r)=>{const i=()=>{t.removeEventListener("success",o),t.removeEventListener("error",l)},o=()=>{n(Tn(t.result)),i()},l=()=>{r(t.error),i()};t.addEventListener("success",o),t.addEventListener("error",l)});return e.then(n=>{n instanceof IDBCursor&&mm.set(n,t)}).catch(()=>{}),Rc.set(e,t),e}function D1(t){if(Tu.has(t))return;const e=new Promise((n,r)=>{const i=()=>{t.removeEventListener("complete",o),t.removeEventListener("error",l),t.removeEventListener("abort",l)},o=()=>{n(),i()},l=()=>{r(t.error||new DOMException("AbortError","AbortError")),i()};t.addEventListener("complete",o),t.addEventListener("error",l),t.addEventListener("abort",l)});Tu.set(t,e)}let ku={get(t,e,n){if(t instanceof IDBTransaction){if(e==="done")return Tu.get(t);if(e==="objectStoreNames")return t.objectStoreNames||ym.get(t);if(e==="store")return n.objectStoreNames[1]?void 0:n.objectStore(n.objectStoreNames[0])}return Tn(t[e])},set(t,e,n){return t[e]=n,!0},has(t,e){return t instanceof IDBTransaction&&(e==="done"||e==="store")?!0:e in t}};function L1(t){ku=t(ku)}function x1(t){return t===IDBDatabase.prototype.transaction&&!("objectStoreNames"in IDBTransaction.prototype)?function(e,...n){const r=t.call(_a(this),e,...n);return ym.set(r,e.sort?e.sort():[e]),Tn(r)}:N1().includes(t)?function(...e){return t.apply(_a(this),e),Tn(mm.get(this))}:function(...e){return Tn(t.apply(_a(this),e))}}function M1(t){return typeof t=="function"?x1(t):(t instanceof IDBTransaction&&D1(t),A1(t,R1())?new Proxy(t,ku):t)}function Tn(t){if(t instanceof IDBRequest)return O1(t);if(va.has(t))return va.get(t);const e=M1(t);return e!==t&&(va.set(t,e),Rc.set(e,t)),e}const _a=t=>Rc.get(t);function U1(t,e,{blocked:n,upgrade:r,blocking:i,terminated:o}={}){const l=indexedDB.open(t,e),u=Tn(l);return r&&l.addEventListener("upgradeneeded",h=>{r(Tn(l.result),h.oldVersion,h.newVersion,Tn(l.transaction),h)}),n&&l.addEventListener("blocked",h=>n(h.oldVersion,h.newVersion,h)),u.then(h=>{o&&h.addEventListener("close",()=>o()),i&&h.addEventListener("versionchange",d=>i(d.oldVersion,d.newVersion,d))}).catch(()=>{}),u}const F1=["get","getKey","getAll","getAllKeys","count"],j1=["put","add","delete","clear"],wa=new Map;function rd(t,e){if(!(t instanceof IDBDatabase&&!(e in t)&&typeof e=="string"))return;if(wa.get(e))return wa.get(e);const n=e.replace(/FromIndex$/,""),r=e!==n,i=j1.includes(n);if(!(n in(r?IDBIndex:IDBObjectStore).prototype)||!(i||F1.includes(n)))return;const o=async function(l,...u){const h=this.transaction(l,i?"readwrite":"readonly");let d=h.store;return r&&(d=d.index(u.shift())),(await Promise.all([d[n](...u),i&&h.done]))[0]};return wa.set(e,o),o}L1(t=>({...t,get:(e,n,r)=>rd(e,n)||t.get(e,n,r),has:(e,n)=>!!rd(e,n)||t.has(e,n)}));/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class V1{constructor(e){this.container=e}getPlatformInfoString(){return this.container.getProviders().map(n=>{if(z1(n)){const r=n.getImmediate();return`${r.library}/${r.version}`}else return null}).filter(n=>n).join(" ")}}function z1(t){const e=t.getComponent();return(e==null?void 0:e.type)==="VERSION"}const Cu="@firebase/app",id="0.14.5";/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Gt=new Ac("@firebase/app"),$1="@firebase/app-compat",b1="@firebase/analytics-compat",B1="@firebase/analytics",H1="@firebase/app-check-compat",W1="@firebase/app-check",G1="@firebase/auth",K1="@firebase/auth-compat",q1="@firebase/database",X1="@firebase/data-connect",J1="@firebase/database-compat",Q1="@firebase/functions",Y1="@firebase/functions-compat",Z1="@firebase/installations",ew="@firebase/installations-compat",tw="@firebase/messaging",nw="@firebase/messaging-compat",rw="@firebase/performance",iw="@firebase/performance-compat",sw="@firebase/remote-config",ow="@firebase/remote-config-compat",lw="@firebase/storage",aw="@firebase/storage-compat",uw="@firebase/firestore",cw="@firebase/ai",hw="@firebase/firestore-compat",fw="firebase",dw="12.5.0";/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Pu="[DEFAULT]",pw={[Cu]:"fire-core",[$1]:"fire-core-compat",[B1]:"fire-analytics",[b1]:"fire-analytics-compat",[W1]:"fire-app-check",[H1]:"fire-app-check-compat",[G1]:"fire-auth",[K1]:"fire-auth-compat",[q1]:"fire-rtdb",[X1]:"fire-data-connect",[J1]:"fire-rtdb-compat",[Q1]:"fire-fn",[Y1]:"fire-fn-compat",[Z1]:"fire-iid",[ew]:"fire-iid-compat",[tw]:"fire-fcm",[nw]:"fire-fcm-compat",[rw]:"fire-perf",[iw]:"fire-perf-compat",[sw]:"fire-rc",[ow]:"fire-rc-compat",[lw]:"fire-gcs",[aw]:"fire-gcs-compat",[uw]:"fire-fst",[hw]:"fire-fst-compat",[cw]:"fire-vertex","fire-js":"fire-js",[fw]:"fire-js-all"};/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Go=new Map,gw=new Map,Au=new Map;function sd(t,e){try{t.container.addComponent(e)}catch(n){Gt.debug(`Component ${e.name} failed to register with FirebaseApp ${t.name}`,n)}}function Gr(t){const e=t.name;if(Au.has(e))return Gt.debug(`There were multiple attempts to register component ${e}.`),!1;Au.set(e,t);for(const n of Go.values())sd(n,t);for(const n of gw.values())sd(n,t);return!0}function Nc(t,e){const n=t.container.getProvider("heartbeat").getImmediate({optional:!0});return n&&n.triggerHeartbeat(),t.container.getProvider(e)}function It(t){return t==null?!1:t.settings!==void 0}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const mw={"no-app":"No Firebase App '{$appName}' has been created - call initializeApp() first","bad-app-name":"Illegal App name: '{$appName}'","duplicate-app":"Firebase App named '{$appName}' already exists with different options or config","app-deleted":"Firebase App named '{$appName}' already deleted","server-app-deleted":"Firebase Server App has been deleted","no-options":"Need to provide options, when not being deployed to hosting via source.","invalid-app-argument":"firebase.{$appName}() takes either no argument or a Firebase App instance.","invalid-log-argument":"First argument to `onLog` must be null or a function.","idb-open":"Error thrown when opening IndexedDB. Original error: {$originalErrorMessage}.","idb-get":"Error thrown when reading from IndexedDB. Original error: {$originalErrorMessage}.","idb-set":"Error thrown when writing to IndexedDB. Original error: {$originalErrorMessage}.","idb-delete":"Error thrown when deleting from IndexedDB. Original error: {$originalErrorMessage}.","finalization-registry-not-supported":"FirebaseServerApp deleteOnDeref field defined but the JS runtime does not support FinalizationRegistry.","invalid-server-app-environment":"FirebaseServerApp is not for use in browser environments."},kn=new Ss("app","Firebase",mw);/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class yw{constructor(e,n,r){this._isDeleted=!1,this._options={...e},this._config={...n},this._name=n.name,this._automaticDataCollectionEnabled=n.automaticDataCollectionEnabled,this._container=r,this.container.addComponent(new or("app",()=>this,"PUBLIC"))}get automaticDataCollectionEnabled(){return this.checkDestroyed(),this._automaticDataCollectionEnabled}set automaticDataCollectionEnabled(e){this.checkDestroyed(),this._automaticDataCollectionEnabled=e}get name(){return this.checkDestroyed(),this._name}get options(){return this.checkDestroyed(),this._options}get config(){return this.checkDestroyed(),this._config}get container(){return this._container}get isDeleted(){return this._isDeleted}set isDeleted(e){this._isDeleted=e}checkDestroyed(){if(this.isDeleted)throw kn.create("app-deleted",{appName:this._name})}}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Zr=dw;function vm(t,e={}){let n=t;typeof e!="object"&&(e={name:e});const r={name:Pu,automaticDataCollectionEnabled:!0,...e},i=r.name;if(typeof i!="string"||!i)throw kn.create("bad-app-name",{appName:String(i)});if(n||(n=fm()),!n)throw kn.create("no-options");const o=Go.get(i);if(o){if(sr(n,o.options)&&sr(r,o.config))return o;throw kn.create("duplicate-app",{appName:i})}const l=new I1(i);for(const h of Au.values())l.addComponent(h);const u=new yw(n,r,l);return Go.set(i,u),u}function _m(t=Pu){const e=Go.get(t);if(!e&&t===Pu&&fm())return vm();if(!e)throw kn.create("no-app",{appName:t});return e}function Cn(t,e,n){let r=pw[t]??t;n&&(r+=`-${n}`);const i=r.match(/\s|\//),o=e.match(/\s|\//);if(i||o){const l=[`Unable to register library "${r}" with version "${e}":`];i&&l.push(`library name "${r}" contains illegal characters (whitespace or "/")`),i&&o&&l.push("and"),o&&l.push(`version name "${e}" contains illegal characters (whitespace or "/")`),Gt.warn(l.join(" "));return}Gr(new or(`${r}-version`,()=>({library:r,version:e}),"VERSION"))}/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const vw="firebase-heartbeat-database",_w=1,fs="firebase-heartbeat-store";let Ea=null;function wm(){return Ea||(Ea=U1(vw,_w,{upgrade:(t,e)=>{switch(e){case 0:try{t.createObjectStore(fs)}catch(n){console.warn(n)}}}}).catch(t=>{throw kn.create("idb-open",{originalErrorMessage:t.message})})),Ea}async function ww(t){try{const n=(await wm()).transaction(fs),r=await n.objectStore(fs).get(Em(t));return await n.done,r}catch(e){if(e instanceof Jt)Gt.warn(e.message);else{const n=kn.create("idb-get",{originalErrorMessage:e==null?void 0:e.message});Gt.warn(n.message)}}}async function od(t,e){try{const r=(await wm()).transaction(fs,"readwrite");await r.objectStore(fs).put(e,Em(t)),await r.done}catch(n){if(n instanceof Jt)Gt.warn(n.message);else{const r=kn.create("idb-set",{originalErrorMessage:n==null?void 0:n.message});Gt.warn(r.message)}}}function Em(t){return`${t.name}!${t.options.appId}`}/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Ew=1024,Sw=30;class Iw{constructor(e){this.container=e,this._heartbeatsCache=null;const n=this.container.getProvider("app").getImmediate();this._storage=new kw(n),this._heartbeatsCachePromise=this._storage.read().then(r=>(this._heartbeatsCache=r,r))}async triggerHeartbeat(){var e,n;try{const i=this.container.getProvider("platform-logger").getImmediate().getPlatformInfoString(),o=ld();if(((e=this._heartbeatsCache)==null?void 0:e.heartbeats)==null&&(this._heartbeatsCache=await this._heartbeatsCachePromise,((n=this._heartbeatsCache)==null?void 0:n.heartbeats)==null)||this._heartbeatsCache.lastSentHeartbeatDate===o||this._heartbeatsCache.heartbeats.some(l=>l.date===o))return;if(this._heartbeatsCache.heartbeats.push({date:o,agent:i}),this._heartbeatsCache.heartbeats.length>Sw){const l=Cw(this._heartbeatsCache.heartbeats);this._heartbeatsCache.heartbeats.splice(l,1)}return this._storage.overwrite(this._heartbeatsCache)}catch(r){Gt.warn(r)}}async getHeartbeatsHeader(){var e;try{if(this._heartbeatsCache===null&&await this._heartbeatsCachePromise,((e=this._heartbeatsCache)==null?void 0:e.heartbeats)==null||this._heartbeatsCache.heartbeats.length===0)return"";const n=ld(),{heartbeatsToSend:r,unsentEntries:i}=Tw(this._heartbeatsCache.heartbeats),o=Wo(JSON.stringify({version:2,heartbeats:r}));return this._heartbeatsCache.lastSentHeartbeatDate=n,i.length>0?(this._heartbeatsCache.heartbeats=i,await this._storage.overwrite(this._heartbeatsCache)):(this._heartbeatsCache.heartbeats=[],this._storage.overwrite(this._heartbeatsCache)),o}catch(n){return Gt.warn(n),""}}}function ld(){return new Date().toISOString().substring(0,10)}function Tw(t,e=Ew){const n=[];let r=t.slice();for(const i of t){const o=n.find(l=>l.agent===i.agent);if(o){if(o.dates.push(i.date),ad(n)>e){o.dates.pop();break}}else if(n.push({agent:i.agent,dates:[i.date]}),ad(n)>e){n.pop();break}r=r.slice(1)}return{heartbeatsToSend:n,unsentEntries:r}}class kw{constructor(e){this.app=e,this._canUseIndexedDBPromise=this.runIndexedDBEnvironmentCheck()}async runIndexedDBEnvironmentCheck(){return h1()?f1().then(()=>!0).catch(()=>!1):!1}async read(){if(await this._canUseIndexedDBPromise){const n=await ww(this.app);return n!=null&&n.heartbeats?n:{heartbeats:[]}}else return{heartbeats:[]}}async overwrite(e){if(await this._canUseIndexedDBPromise){const r=await this.read();return od(this.app,{lastSentHeartbeatDate:e.lastSentHeartbeatDate??r.lastSentHeartbeatDate,heartbeats:e.heartbeats})}else return}async add(e){if(await this._canUseIndexedDBPromise){const r=await this.read();return od(this.app,{lastSentHeartbeatDate:e.lastSentHeartbeatDate??r.lastSentHeartbeatDate,heartbeats:[...r.heartbeats,...e.heartbeats]})}else return}}function ad(t){return Wo(JSON.stringify({version:2,heartbeats:t})).length}function Cw(t){if(t.length===0)return-1;let e=0,n=t[0].date;for(let r=1;r<t.length;r++)t[r].date<n&&(n=t[r].date,e=r);return e}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function Pw(t){Gr(new or("platform-logger",e=>new V1(e),"PRIVATE")),Gr(new or("heartbeat",e=>new Iw(e),"PRIVATE")),Cn(Cu,id,t),Cn(Cu,id,"esm2020"),Cn("fire-js","")}Pw("");function Sm(){return{"dependent-sdk-initialized-before-auth":"Another Firebase SDK was initialized and is trying to use Auth before Auth is initialized. Please be sure to call `initializeAuth` or `getAuth` before starting any other Firebase SDK."}}const Aw=Sm,Im=new Ss("auth","Firebase",Sm());/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Ko=new Ac("@firebase/auth");function Rw(t,...e){Ko.logLevel<=J.WARN&&Ko.warn(`Auth (${Zr}): ${t}`,...e)}function mo(t,...e){Ko.logLevel<=J.ERROR&&Ko.error(`Auth (${Zr}): ${t}`,...e)}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function gt(t,...e){throw Oc(t,...e)}function Pt(t,...e){return Oc(t,...e)}function Tm(t,e,n){const r={...Aw(),[e]:n};return new Ss("auth","Firebase",r).create(e,{appName:t.name})}function Qn(t){return Tm(t,"operation-not-supported-in-this-environment","Operations that alter the current user are not supported in conjunction with FirebaseServerApp")}function Oc(t,...e){if(typeof t!="string"){const n=e[0],r=[...e.slice(1)];return r[0]&&(r[0].appName=t.name),t._errorFactory.create(n,...r)}return Im.create(t,...e)}function V(t,e,...n){if(!t)throw Oc(e,...n)}function jt(t){const e="INTERNAL ASSERTION FAILED: "+t;throw mo(e),new Error(e)}function Kt(t,e){t||jt(e)}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function Ru(){var t;return typeof self<"u"&&((t=self.location)==null?void 0:t.href)||""}function Nw(){return ud()==="http:"||ud()==="https:"}function ud(){var t;return typeof self<"u"&&((t=self.location)==null?void 0:t.protocol)||null}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function Ow(){return typeof navigator<"u"&&navigator&&"onLine"in navigator&&typeof navigator.onLine=="boolean"&&(Nw()||a1()||"connection"in navigator)?navigator.onLine:!0}function Dw(){if(typeof navigator>"u")return null;const t=navigator;return t.languages&&t.languages[0]||t.language||null}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Ts{constructor(e,n){this.shortDelay=e,this.longDelay=n,Kt(n>e,"Short delay should be less than long delay!"),this.isMobile=o1()||u1()}get(){return Ow()?this.isMobile?this.longDelay:this.shortDelay:Math.min(5e3,this.shortDelay)}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function Dc(t,e){Kt(t.emulator,"Emulator should always be set here");const{url:n}=t.emulator;return e?`${n}${e.startsWith("/")?e.slice(1):e}`:n}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class km{static initialize(e,n,r){this.fetchImpl=e,n&&(this.headersImpl=n),r&&(this.responseImpl=r)}static fetch(){if(this.fetchImpl)return this.fetchImpl;if(typeof self<"u"&&"fetch"in self)return self.fetch;if(typeof globalThis<"u"&&globalThis.fetch)return globalThis.fetch;if(typeof fetch<"u")return fetch;jt("Could not find fetch implementation, make sure you call FetchProvider.initialize() with an appropriate polyfill")}static headers(){if(this.headersImpl)return this.headersImpl;if(typeof self<"u"&&"Headers"in self)return self.Headers;if(typeof globalThis<"u"&&globalThis.Headers)return globalThis.Headers;if(typeof Headers<"u")return Headers;jt("Could not find Headers implementation, make sure you call FetchProvider.initialize() with an appropriate polyfill")}static response(){if(this.responseImpl)return this.responseImpl;if(typeof self<"u"&&"Response"in self)return self.Response;if(typeof globalThis<"u"&&globalThis.Response)return globalThis.Response;if(typeof Response<"u")return Response;jt("Could not find Response implementation, make sure you call FetchProvider.initialize() with an appropriate polyfill")}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Lw={CREDENTIAL_MISMATCH:"custom-token-mismatch",MISSING_CUSTOM_TOKEN:"internal-error",INVALID_IDENTIFIER:"invalid-email",MISSING_CONTINUE_URI:"internal-error",INVALID_PASSWORD:"wrong-password",MISSING_PASSWORD:"missing-password",INVALID_LOGIN_CREDENTIALS:"invalid-credential",EMAIL_EXISTS:"email-already-in-use",PASSWORD_LOGIN_DISABLED:"operation-not-allowed",INVALID_IDP_RESPONSE:"invalid-credential",INVALID_PENDING_TOKEN:"invalid-credential",FEDERATED_USER_ID_ALREADY_LINKED:"credential-already-in-use",MISSING_REQ_TYPE:"internal-error",EMAIL_NOT_FOUND:"user-not-found",RESET_PASSWORD_EXCEED_LIMIT:"too-many-requests",EXPIRED_OOB_CODE:"expired-action-code",INVALID_OOB_CODE:"invalid-action-code",MISSING_OOB_CODE:"internal-error",CREDENTIAL_TOO_OLD_LOGIN_AGAIN:"requires-recent-login",INVALID_ID_TOKEN:"invalid-user-token",TOKEN_EXPIRED:"user-token-expired",USER_NOT_FOUND:"user-token-expired",TOO_MANY_ATTEMPTS_TRY_LATER:"too-many-requests",PASSWORD_DOES_NOT_MEET_REQUIREMENTS:"password-does-not-meet-requirements",INVALID_CODE:"invalid-verification-code",INVALID_SESSION_INFO:"invalid-verification-id",INVALID_TEMPORARY_PROOF:"invalid-credential",MISSING_SESSION_INFO:"missing-verification-id",SESSION_EXPIRED:"code-expired",MISSING_ANDROID_PACKAGE_NAME:"missing-android-pkg-name",UNAUTHORIZED_DOMAIN:"unauthorized-continue-uri",INVALID_OAUTH_CLIENT_ID:"invalid-oauth-client-id",ADMIN_ONLY_OPERATION:"admin-restricted-operation",INVALID_MFA_PENDING_CREDENTIAL:"invalid-multi-factor-session",MFA_ENROLLMENT_NOT_FOUND:"multi-factor-info-not-found",MISSING_MFA_ENROLLMENT_ID:"missing-multi-factor-info",MISSING_MFA_PENDING_CREDENTIAL:"missing-multi-factor-session",SECOND_FACTOR_EXISTS:"second-factor-already-in-use",SECOND_FACTOR_LIMIT_EXCEEDED:"maximum-second-factor-count-exceeded",BLOCKING_FUNCTION_ERROR_RESPONSE:"internal-error",RECAPTCHA_NOT_ENABLED:"recaptcha-not-enabled",MISSING_RECAPTCHA_TOKEN:"missing-recaptcha-token",INVALID_RECAPTCHA_TOKEN:"invalid-recaptcha-token",INVALID_RECAPTCHA_ACTION:"invalid-recaptcha-action",MISSING_CLIENT_TYPE:"missing-client-type",MISSING_RECAPTCHA_VERSION:"missing-recaptcha-version",INVALID_RECAPTCHA_VERSION:"invalid-recaptcha-version",INVALID_REQ_TYPE:"invalid-req-type"};/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const xw=["/v1/accounts:signInWithCustomToken","/v1/accounts:signInWithEmailLink","/v1/accounts:signInWithIdp","/v1/accounts:signInWithPassword","/v1/accounts:signInWithPhoneNumber","/v1/token"],Mw=new Ts(3e4,6e4);function cr(t,e){return t.tenantId&&!e.tenantId?{...e,tenantId:t.tenantId}:e}async function xn(t,e,n,r,i={}){return Cm(t,i,async()=>{let o={},l={};r&&(e==="GET"?l=r:o={body:JSON.stringify(r)});const u=Is({key:t.config.apiKey,...l}).slice(1),h=await t._getAdditionalHeaders();h["Content-Type"]="application/json",t.languageCode&&(h["X-Firebase-Locale"]=t.languageCode);const d={method:e,headers:h,...o};return l1()||(d.referrerPolicy="no-referrer"),t.emulatorConfig&&Es(t.emulatorConfig.host)&&(d.credentials="include"),km.fetch()(await Pm(t,t.config.apiHost,n,u),d)})}async function Cm(t,e,n){t._canInitEmulator=!1;const r={...Lw,...e};try{const i=new Fw(t),o=await Promise.race([n(),i.promise]);i.clearNetworkTimeout();const l=await o.json();if("needConfirmation"in l)throw eo(t,"account-exists-with-different-credential",l);if(o.ok&&!("errorMessage"in l))return l;{const u=o.ok?l.errorMessage:l.error.message,[h,d]=u.split(" : ");if(h==="FEDERATED_USER_ID_ALREADY_LINKED")throw eo(t,"credential-already-in-use",l);if(h==="EMAIL_EXISTS")throw eo(t,"email-already-in-use",l);if(h==="USER_DISABLED")throw eo(t,"user-disabled",l);const k=r[h]||h.toLowerCase().replace(/[_\s]+/g,"-");if(d)throw Tm(t,k,d);gt(t,k)}}catch(i){if(i instanceof Jt)throw i;gt(t,"network-request-failed",{message:String(i)})}}async function yl(t,e,n,r,i={}){const o=await xn(t,e,n,r,i);return"mfaPendingCredential"in o&&gt(t,"multi-factor-auth-required",{_serverResponse:o}),o}async function Pm(t,e,n,r){const i=`${e}${n}?${r}`,o=t,l=o.config.emulator?Dc(t.config,i):`${t.config.apiScheme}://${i}`;return xw.includes(n)&&(await o._persistenceManagerAvailable,o._getPersistenceType()==="COOKIE")?o._getPersistence()._getFinalTarget(l).toString():l}function Uw(t){switch(t){case"ENFORCE":return"ENFORCE";case"AUDIT":return"AUDIT";case"OFF":return"OFF";default:return"ENFORCEMENT_STATE_UNSPECIFIED"}}class Fw{clearNetworkTimeout(){clearTimeout(this.timer)}constructor(e){this.auth=e,this.timer=null,this.promise=new Promise((n,r)=>{this.timer=setTimeout(()=>r(Pt(this.auth,"network-request-failed")),Mw.get())})}}function eo(t,e,n){const r={appName:t.name};n.email&&(r.email=n.email),n.phoneNumber&&(r.phoneNumber=n.phoneNumber);const i=Pt(t,e,r);return i.customData._tokenResponse=n,i}function cd(t){return t!==void 0&&t.enterprise!==void 0}class jw{constructor(e){if(this.siteKey="",this.recaptchaEnforcementState=[],e.recaptchaKey===void 0)throw new Error("recaptchaKey undefined");this.siteKey=e.recaptchaKey.split("/")[3],this.recaptchaEnforcementState=e.recaptchaEnforcementState}getProviderEnforcementState(e){if(!this.recaptchaEnforcementState||this.recaptchaEnforcementState.length===0)return null;for(const n of this.recaptchaEnforcementState)if(n.provider&&n.provider===e)return Uw(n.enforcementState);return null}isProviderEnabled(e){return this.getProviderEnforcementState(e)==="ENFORCE"||this.getProviderEnforcementState(e)==="AUDIT"}isAnyProviderEnabled(){return this.isProviderEnabled("EMAIL_PASSWORD_PROVIDER")||this.isProviderEnabled("PHONE_PROVIDER")}}async function Vw(t,e){return xn(t,"GET","/v2/recaptchaConfig",cr(t,e))}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */async function zw(t,e){return xn(t,"POST","/v1/accounts:delete",e)}async function qo(t,e){return xn(t,"POST","/v1/accounts:lookup",e)}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function Hi(t){if(t)try{const e=new Date(Number(t));if(!isNaN(e.getTime()))return e.toUTCString()}catch{}}async function $w(t,e=!1){const n=Yr(t),r=await n.getIdToken(e),i=Lc(r);V(i&&i.exp&&i.auth_time&&i.iat,n.auth,"internal-error");const o=typeof i.firebase=="object"?i.firebase:void 0,l=o==null?void 0:o.sign_in_provider;return{claims:i,token:r,authTime:Hi(Sa(i.auth_time)),issuedAtTime:Hi(Sa(i.iat)),expirationTime:Hi(Sa(i.exp)),signInProvider:l||null,signInSecondFactor:(o==null?void 0:o.sign_in_second_factor)||null}}function Sa(t){return Number(t)*1e3}function Lc(t){const[e,n,r]=t.split(".");if(e===void 0||n===void 0||r===void 0)return mo("JWT malformed, contained fewer than 3 sections"),null;try{const i=cm(n);return i?JSON.parse(i):(mo("Failed to decode base64 JWT payload"),null)}catch(i){return mo("Caught error parsing JWT payload as JSON",i==null?void 0:i.toString()),null}}function hd(t){const e=Lc(t);return V(e,"internal-error"),V(typeof e.exp<"u","internal-error"),V(typeof e.iat<"u","internal-error"),Number(e.exp)-Number(e.iat)}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */async function ds(t,e,n=!1){if(n)return e;try{return await e}catch(r){throw r instanceof Jt&&bw(r)&&t.auth.currentUser===t&&await t.auth.signOut(),r}}function bw({code:t}){return t==="auth/user-disabled"||t==="auth/user-token-expired"}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Bw{constructor(e){this.user=e,this.isRunning=!1,this.timerId=null,this.errorBackoff=3e4}_start(){this.isRunning||(this.isRunning=!0,this.schedule())}_stop(){this.isRunning&&(this.isRunning=!1,this.timerId!==null&&clearTimeout(this.timerId))}getInterval(e){if(e){const n=this.errorBackoff;return this.errorBackoff=Math.min(this.errorBackoff*2,96e4),n}else{this.errorBackoff=3e4;const r=(this.user.stsTokenManager.expirationTime??0)-Date.now()-3e5;return Math.max(0,r)}}schedule(e=!1){if(!this.isRunning)return;const n=this.getInterval(e);this.timerId=setTimeout(async()=>{await this.iteration()},n)}async iteration(){try{await this.user.getIdToken(!0)}catch(e){(e==null?void 0:e.code)==="auth/network-request-failed"&&this.schedule(!0);return}this.schedule()}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Nu{constructor(e,n){this.createdAt=e,this.lastLoginAt=n,this._initializeTime()}_initializeTime(){this.lastSignInTime=Hi(this.lastLoginAt),this.creationTime=Hi(this.createdAt)}_copy(e){this.createdAt=e.createdAt,this.lastLoginAt=e.lastLoginAt,this._initializeTime()}toJSON(){return{createdAt:this.createdAt,lastLoginAt:this.lastLoginAt}}}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */async function Xo(t){var S;const e=t.auth,n=await t.getIdToken(),r=await ds(t,qo(e,{idToken:n}));V(r==null?void 0:r.users.length,e,"internal-error");const i=r.users[0];t._notifyReloadListener(i);const o=(S=i.providerUserInfo)!=null&&S.length?Am(i.providerUserInfo):[],l=Ww(t.providerData,o),u=t.isAnonymous,h=!(t.email&&i.passwordHash)&&!(l!=null&&l.length),d=u?h:!1,k={uid:i.localId,displayName:i.displayName||null,photoURL:i.photoUrl||null,email:i.email||null,emailVerified:i.emailVerified||!1,phoneNumber:i.phoneNumber||null,tenantId:i.tenantId||null,providerData:l,metadata:new Nu(i.createdAt,i.lastLoginAt),isAnonymous:d};Object.assign(t,k)}async function Hw(t){const e=Yr(t);await Xo(e),await e.auth._persistUserIfCurrent(e),e.auth._notifyListenersIfCurrent(e)}function Ww(t,e){return[...t.filter(r=>!e.some(i=>i.providerId===r.providerId)),...e]}function Am(t){return t.map(({providerId:e,...n})=>({providerId:e,uid:n.rawId||"",displayName:n.displayName||null,email:n.email||null,phoneNumber:n.phoneNumber||null,photoURL:n.photoUrl||null}))}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */async function Gw(t,e){const n=await Cm(t,{},async()=>{const r=Is({grant_type:"refresh_token",refresh_token:e}).slice(1),{tokenApiHost:i,apiKey:o}=t.config,l=await Pm(t,i,"/v1/token",`key=${o}`),u=await t._getAdditionalHeaders();u["Content-Type"]="application/x-www-form-urlencoded";const h={method:"POST",headers:u,body:r};return t.emulatorConfig&&Es(t.emulatorConfig.host)&&(h.credentials="include"),km.fetch()(l,h)});return{accessToken:n.access_token,expiresIn:n.expires_in,refreshToken:n.refresh_token}}async function Kw(t,e){return xn(t,"POST","/v2/accounts:revokeToken",cr(t,e))}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Mr{constructor(){this.refreshToken=null,this.accessToken=null,this.expirationTime=null}get isExpired(){return!this.expirationTime||Date.now()>this.expirationTime-3e4}updateFromServerResponse(e){V(e.idToken,"internal-error"),V(typeof e.idToken<"u","internal-error"),V(typeof e.refreshToken<"u","internal-error");const n="expiresIn"in e&&typeof e.expiresIn<"u"?Number(e.expiresIn):hd(e.idToken);this.updateTokensAndExpiration(e.idToken,e.refreshToken,n)}updateFromIdToken(e){V(e.length!==0,"internal-error");const n=hd(e);this.updateTokensAndExpiration(e,null,n)}async getToken(e,n=!1){return!n&&this.accessToken&&!this.isExpired?this.accessToken:(V(this.refreshToken,e,"user-token-expired"),this.refreshToken?(await this.refresh(e,this.refreshToken),this.accessToken):null)}clearRefreshToken(){this.refreshToken=null}async refresh(e,n){const{accessToken:r,refreshToken:i,expiresIn:o}=await Gw(e,n);this.updateTokensAndExpiration(r,i,Number(o))}updateTokensAndExpiration(e,n,r){this.refreshToken=n||null,this.accessToken=e||null,this.expirationTime=Date.now()+r*1e3}static fromJSON(e,n){const{refreshToken:r,accessToken:i,expirationTime:o}=n,l=new Mr;return r&&(V(typeof r=="string","internal-error",{appName:e}),l.refreshToken=r),i&&(V(typeof i=="string","internal-error",{appName:e}),l.accessToken=i),o&&(V(typeof o=="number","internal-error",{appName:e}),l.expirationTime=o),l}toJSON(){return{refreshToken:this.refreshToken,accessToken:this.accessToken,expirationTime:this.expirationTime}}_assign(e){this.accessToken=e.accessToken,this.refreshToken=e.refreshToken,this.expirationTime=e.expirationTime}_clone(){return Object.assign(new Mr,this.toJSON())}_performRefresh(){return jt("not implemented")}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function on(t,e){V(typeof t=="string"||typeof t>"u","internal-error",{appName:e})}class ct{constructor({uid:e,auth:n,stsTokenManager:r,...i}){this.providerId="firebase",this.proactiveRefresh=new Bw(this),this.reloadUserInfo=null,this.reloadListener=null,this.uid=e,this.auth=n,this.stsTokenManager=r,this.accessToken=r.accessToken,this.displayName=i.displayName||null,this.email=i.email||null,this.emailVerified=i.emailVerified||!1,this.phoneNumber=i.phoneNumber||null,this.photoURL=i.photoURL||null,this.isAnonymous=i.isAnonymous||!1,this.tenantId=i.tenantId||null,this.providerData=i.providerData?[...i.providerData]:[],this.metadata=new Nu(i.createdAt||void 0,i.lastLoginAt||void 0)}async getIdToken(e){const n=await ds(this,this.stsTokenManager.getToken(this.auth,e));return V(n,this.auth,"internal-error"),this.accessToken!==n&&(this.accessToken=n,await this.auth._persistUserIfCurrent(this),this.auth._notifyListenersIfCurrent(this)),n}getIdTokenResult(e){return $w(this,e)}reload(){return Hw(this)}_assign(e){this!==e&&(V(this.uid===e.uid,this.auth,"internal-error"),this.displayName=e.displayName,this.photoURL=e.photoURL,this.email=e.email,this.emailVerified=e.emailVerified,this.phoneNumber=e.phoneNumber,this.isAnonymous=e.isAnonymous,this.tenantId=e.tenantId,this.providerData=e.providerData.map(n=>({...n})),this.metadata._copy(e.metadata),this.stsTokenManager._assign(e.stsTokenManager))}_clone(e){const n=new ct({...this,auth:e,stsTokenManager:this.stsTokenManager._clone()});return n.metadata._copy(this.metadata),n}_onReload(e){V(!this.reloadListener,this.auth,"internal-error"),this.reloadListener=e,this.reloadUserInfo&&(this._notifyReloadListener(this.reloadUserInfo),this.reloadUserInfo=null)}_notifyReloadListener(e){this.reloadListener?this.reloadListener(e):this.reloadUserInfo=e}_startProactiveRefresh(){this.proactiveRefresh._start()}_stopProactiveRefresh(){this.proactiveRefresh._stop()}async _updateTokensIfNecessary(e,n=!1){let r=!1;e.idToken&&e.idToken!==this.stsTokenManager.accessToken&&(this.stsTokenManager.updateFromServerResponse(e),r=!0),n&&await Xo(this),await this.auth._persistUserIfCurrent(this),r&&this.auth._notifyListenersIfCurrent(this)}async delete(){if(It(this.auth.app))return Promise.reject(Qn(this.auth));const e=await this.getIdToken();return await ds(this,zw(this.auth,{idToken:e})),this.stsTokenManager.clearRefreshToken(),this.auth.signOut()}toJSON(){return{uid:this.uid,email:this.email||void 0,emailVerified:this.emailVerified,displayName:this.displayName||void 0,isAnonymous:this.isAnonymous,photoURL:this.photoURL||void 0,phoneNumber:this.phoneNumber||void 0,tenantId:this.tenantId||void 0,providerData:this.providerData.map(e=>({...e})),stsTokenManager:this.stsTokenManager.toJSON(),_redirectEventId:this._redirectEventId,...this.metadata.toJSON(),apiKey:this.auth.config.apiKey,appName:this.auth.name}}get refreshToken(){return this.stsTokenManager.refreshToken||""}static _fromJSON(e,n){const r=n.displayName??void 0,i=n.email??void 0,o=n.phoneNumber??void 0,l=n.photoURL??void 0,u=n.tenantId??void 0,h=n._redirectEventId??void 0,d=n.createdAt??void 0,k=n.lastLoginAt??void 0,{uid:S,emailVerified:E,isAnonymous:N,providerData:O,stsTokenManager:L}=n;V(S&&L,e,"internal-error");const z=Mr.fromJSON(this.name,L);V(typeof S=="string",e,"internal-error"),on(r,e.name),on(i,e.name),V(typeof E=="boolean",e,"internal-error"),V(typeof N=="boolean",e,"internal-error"),on(o,e.name),on(l,e.name),on(u,e.name),on(h,e.name),on(d,e.name),on(k,e.name);const I=new ct({uid:S,auth:e,email:i,emailVerified:E,displayName:r,isAnonymous:N,photoURL:l,phoneNumber:o,tenantId:u,stsTokenManager:z,createdAt:d,lastLoginAt:k});return O&&Array.isArray(O)&&(I.providerData=O.map(_=>({..._}))),h&&(I._redirectEventId=h),I}static async _fromIdTokenResponse(e,n,r=!1){const i=new Mr;i.updateFromServerResponse(n);const o=new ct({uid:n.localId,auth:e,stsTokenManager:i,isAnonymous:r});return await Xo(o),o}static async _fromGetAccountInfoResponse(e,n,r){const i=n.users[0];V(i.localId!==void 0,"internal-error");const o=i.providerUserInfo!==void 0?Am(i.providerUserInfo):[],l=!(i.email&&i.passwordHash)&&!(o!=null&&o.length),u=new Mr;u.updateFromIdToken(r);const h=new ct({uid:i.localId,auth:e,stsTokenManager:u,isAnonymous:l}),d={uid:i.localId,displayName:i.displayName||null,photoURL:i.photoUrl||null,email:i.email||null,emailVerified:i.emailVerified||!1,phoneNumber:i.phoneNumber||null,tenantId:i.tenantId||null,providerData:o,metadata:new Nu(i.createdAt,i.lastLoginAt),isAnonymous:!(i.email&&i.passwordHash)&&!(o!=null&&o.length)};return Object.assign(h,d),h}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const fd=new Map;function Vt(t){Kt(t instanceof Function,"Expected a class definition");let e=fd.get(t);return e?(Kt(e instanceof t,"Instance stored in cache mismatched with class"),e):(e=new t,fd.set(t,e),e)}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Rm{constructor(){this.type="NONE",this.storage={}}async _isAvailable(){return!0}async _set(e,n){this.storage[e]=n}async _get(e){const n=this.storage[e];return n===void 0?null:n}async _remove(e){delete this.storage[e]}_addListener(e,n){}_removeListener(e,n){}}Rm.type="NONE";const dd=Rm;/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function yo(t,e,n){return`firebase:${t}:${e}:${n}`}class Ur{constructor(e,n,r){this.persistence=e,this.auth=n,this.userKey=r;const{config:i,name:o}=this.auth;this.fullUserKey=yo(this.userKey,i.apiKey,o),this.fullPersistenceKey=yo("persistence",i.apiKey,o),this.boundEventHandler=n._onStorageEvent.bind(n),this.persistence._addListener(this.fullUserKey,this.boundEventHandler)}setCurrentUser(e){return this.persistence._set(this.fullUserKey,e.toJSON())}async getCurrentUser(){const e=await this.persistence._get(this.fullUserKey);if(!e)return null;if(typeof e=="string"){const n=await qo(this.auth,{idToken:e}).catch(()=>{});return n?ct._fromGetAccountInfoResponse(this.auth,n,e):null}return ct._fromJSON(this.auth,e)}removeCurrentUser(){return this.persistence._remove(this.fullUserKey)}savePersistenceForRedirect(){return this.persistence._set(this.fullPersistenceKey,this.persistence.type)}async setPersistence(e){if(this.persistence===e)return;const n=await this.getCurrentUser();if(await this.removeCurrentUser(),this.persistence=e,n)return this.setCurrentUser(n)}delete(){this.persistence._removeListener(this.fullUserKey,this.boundEventHandler)}static async create(e,n,r="authUser"){if(!n.length)return new Ur(Vt(dd),e,r);const i=(await Promise.all(n.map(async d=>{if(await d._isAvailable())return d}))).filter(d=>d);let o=i[0]||Vt(dd);const l=yo(r,e.config.apiKey,e.name);let u=null;for(const d of n)try{const k=await d._get(l);if(k){let S;if(typeof k=="string"){const E=await qo(e,{idToken:k}).catch(()=>{});if(!E)break;S=await ct._fromGetAccountInfoResponse(e,E,k)}else S=ct._fromJSON(e,k);d!==o&&(u=S),o=d;break}}catch{}const h=i.filter(d=>d._shouldAllowMigration);return!o._shouldAllowMigration||!h.length?new Ur(o,e,r):(o=h[0],u&&await o._set(l,u.toJSON()),await Promise.all(n.map(async d=>{if(d!==o)try{await d._remove(l)}catch{}})),new Ur(o,e,r))}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function pd(t){const e=t.toLowerCase();if(e.includes("opera/")||e.includes("opr/")||e.includes("opios/"))return"Opera";if(Lm(e))return"IEMobile";if(e.includes("msie")||e.includes("trident/"))return"IE";if(e.includes("edge/"))return"Edge";if(Nm(e))return"Firefox";if(e.includes("silk/"))return"Silk";if(Mm(e))return"Blackberry";if(Um(e))return"Webos";if(Om(e))return"Safari";if((e.includes("chrome/")||Dm(e))&&!e.includes("edge/"))return"Chrome";if(xm(e))return"Android";{const n=/([a-zA-Z\d\.]+)\/[a-zA-Z\d\.]*$/,r=t.match(n);if((r==null?void 0:r.length)===2)return r[1]}return"Other"}function Nm(t=Me()){return/firefox\//i.test(t)}function Om(t=Me()){const e=t.toLowerCase();return e.includes("safari/")&&!e.includes("chrome/")&&!e.includes("crios/")&&!e.includes("android")}function Dm(t=Me()){return/crios\//i.test(t)}function Lm(t=Me()){return/iemobile/i.test(t)}function xm(t=Me()){return/android/i.test(t)}function Mm(t=Me()){return/blackberry/i.test(t)}function Um(t=Me()){return/webos/i.test(t)}function xc(t=Me()){return/iphone|ipad|ipod/i.test(t)||/macintosh/i.test(t)&&/mobile/i.test(t)}function qw(t=Me()){var e;return xc(t)&&!!((e=window.navigator)!=null&&e.standalone)}function Xw(){return c1()&&document.documentMode===10}function Fm(t=Me()){return xc(t)||xm(t)||Um(t)||Mm(t)||/windows phone/i.test(t)||Lm(t)}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function jm(t,e=[]){let n;switch(t){case"Browser":n=pd(Me());break;case"Worker":n=`${pd(Me())}-${t}`;break;default:n=t}const r=e.length?e.join(","):"FirebaseCore-web";return`${n}/JsCore/${Zr}/${r}`}/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Jw{constructor(e){this.auth=e,this.queue=[]}pushCallback(e,n){const r=o=>new Promise((l,u)=>{try{const h=e(o);l(h)}catch(h){u(h)}});r.onAbort=n,this.queue.push(r);const i=this.queue.length-1;return()=>{this.queue[i]=()=>Promise.resolve()}}async runMiddleware(e){if(this.auth.currentUser===e)return;const n=[];try{for(const r of this.queue)await r(e),r.onAbort&&n.push(r.onAbort)}catch(r){n.reverse();for(const i of n)try{i()}catch{}throw this.auth._errorFactory.create("login-blocked",{originalMessage:r==null?void 0:r.message})}}}/**
 * @license
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */async function Qw(t,e={}){return xn(t,"GET","/v2/passwordPolicy",cr(t,e))}/**
 * @license
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Yw=6;class Zw{constructor(e){var r;const n=e.customStrengthOptions;this.customStrengthOptions={},this.customStrengthOptions.minPasswordLength=n.minPasswordLength??Yw,n.maxPasswordLength&&(this.customStrengthOptions.maxPasswordLength=n.maxPasswordLength),n.containsLowercaseCharacter!==void 0&&(this.customStrengthOptions.containsLowercaseLetter=n.containsLowercaseCharacter),n.containsUppercaseCharacter!==void 0&&(this.customStrengthOptions.containsUppercaseLetter=n.containsUppercaseCharacter),n.containsNumericCharacter!==void 0&&(this.customStrengthOptions.containsNumericCharacter=n.containsNumericCharacter),n.containsNonAlphanumericCharacter!==void 0&&(this.customStrengthOptions.containsNonAlphanumericCharacter=n.containsNonAlphanumericCharacter),this.enforcementState=e.enforcementState,this.enforcementState==="ENFORCEMENT_STATE_UNSPECIFIED"&&(this.enforcementState="OFF"),this.allowedNonAlphanumericCharacters=((r=e.allowedNonAlphanumericCharacters)==null?void 0:r.join(""))??"",this.forceUpgradeOnSignin=e.forceUpgradeOnSignin??!1,this.schemaVersion=e.schemaVersion}validatePassword(e){const n={isValid:!0,passwordPolicy:this};return this.validatePasswordLengthOptions(e,n),this.validatePasswordCharacterOptions(e,n),n.isValid&&(n.isValid=n.meetsMinPasswordLength??!0),n.isValid&&(n.isValid=n.meetsMaxPasswordLength??!0),n.isValid&&(n.isValid=n.containsLowercaseLetter??!0),n.isValid&&(n.isValid=n.containsUppercaseLetter??!0),n.isValid&&(n.isValid=n.containsNumericCharacter??!0),n.isValid&&(n.isValid=n.containsNonAlphanumericCharacter??!0),n}validatePasswordLengthOptions(e,n){const r=this.customStrengthOptions.minPasswordLength,i=this.customStrengthOptions.maxPasswordLength;r&&(n.meetsMinPasswordLength=e.length>=r),i&&(n.meetsMaxPasswordLength=e.length<=i)}validatePasswordCharacterOptions(e,n){this.updatePasswordCharacterOptionsStatuses(n,!1,!1,!1,!1);let r;for(let i=0;i<e.length;i++)r=e.charAt(i),this.updatePasswordCharacterOptionsStatuses(n,r>="a"&&r<="z",r>="A"&&r<="Z",r>="0"&&r<="9",this.allowedNonAlphanumericCharacters.includes(r))}updatePasswordCharacterOptionsStatuses(e,n,r,i,o){this.customStrengthOptions.containsLowercaseLetter&&(e.containsLowercaseLetter||(e.containsLowercaseLetter=n)),this.customStrengthOptions.containsUppercaseLetter&&(e.containsUppercaseLetter||(e.containsUppercaseLetter=r)),this.customStrengthOptions.containsNumericCharacter&&(e.containsNumericCharacter||(e.containsNumericCharacter=i)),this.customStrengthOptions.containsNonAlphanumericCharacter&&(e.containsNonAlphanumericCharacter||(e.containsNonAlphanumericCharacter=o))}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class eE{constructor(e,n,r,i){this.app=e,this.heartbeatServiceProvider=n,this.appCheckServiceProvider=r,this.config=i,this.currentUser=null,this.emulatorConfig=null,this.operations=Promise.resolve(),this.authStateSubscription=new gd(this),this.idTokenSubscription=new gd(this),this.beforeStateQueue=new Jw(this),this.redirectUser=null,this.isProactiveRefreshEnabled=!1,this.EXPECTED_PASSWORD_POLICY_SCHEMA_VERSION=1,this._canInitEmulator=!0,this._isInitialized=!1,this._deleted=!1,this._initializationPromise=null,this._popupRedirectResolver=null,this._errorFactory=Im,this._agentRecaptchaConfig=null,this._tenantRecaptchaConfigs={},this._projectPasswordPolicy=null,this._tenantPasswordPolicies={},this._resolvePersistenceManagerAvailable=void 0,this.lastNotifiedUid=void 0,this.languageCode=null,this.tenantId=null,this.settings={appVerificationDisabledForTesting:!1},this.frameworks=[],this.name=e.name,this.clientVersion=i.sdkClientVersion,this._persistenceManagerAvailable=new Promise(o=>this._resolvePersistenceManagerAvailable=o)}_initializeWithPersistence(e,n){return n&&(this._popupRedirectResolver=Vt(n)),this._initializationPromise=this.queue(async()=>{var r,i,o;if(!this._deleted&&(this.persistenceManager=await Ur.create(this,e),(r=this._resolvePersistenceManagerAvailable)==null||r.call(this),!this._deleted)){if((i=this._popupRedirectResolver)!=null&&i._shouldInitProactively)try{await this._popupRedirectResolver._initialize(this)}catch{}await this.initializeCurrentUser(n),this.lastNotifiedUid=((o=this.currentUser)==null?void 0:o.uid)||null,!this._deleted&&(this._isInitialized=!0)}}),this._initializationPromise}async _onStorageEvent(){if(this._deleted)return;const e=await this.assertedPersistence.getCurrentUser();if(!(!this.currentUser&&!e)){if(this.currentUser&&e&&this.currentUser.uid===e.uid){this._currentUser._assign(e),await this.currentUser.getIdToken();return}await this._updateCurrentUser(e,!0)}}async initializeCurrentUserFromIdToken(e){try{const n=await qo(this,{idToken:e}),r=await ct._fromGetAccountInfoResponse(this,n,e);await this.directlySetCurrentUser(r)}catch(n){console.warn("FirebaseServerApp could not login user with provided authIdToken: ",n),await this.directlySetCurrentUser(null)}}async initializeCurrentUser(e){var o;if(It(this.app)){const l=this.app.settings.authIdToken;return l?new Promise(u=>{setTimeout(()=>this.initializeCurrentUserFromIdToken(l).then(u,u))}):this.directlySetCurrentUser(null)}const n=await this.assertedPersistence.getCurrentUser();let r=n,i=!1;if(e&&this.config.authDomain){await this.getOrInitRedirectPersistenceManager();const l=(o=this.redirectUser)==null?void 0:o._redirectEventId,u=r==null?void 0:r._redirectEventId,h=await this.tryRedirectSignIn(e);(!l||l===u)&&(h!=null&&h.user)&&(r=h.user,i=!0)}if(!r)return this.directlySetCurrentUser(null);if(!r._redirectEventId){if(i)try{await this.beforeStateQueue.runMiddleware(r)}catch(l){r=n,this._popupRedirectResolver._overrideRedirectResult(this,()=>Promise.reject(l))}return r?this.reloadAndSetCurrentUserOrClear(r):this.directlySetCurrentUser(null)}return V(this._popupRedirectResolver,this,"argument-error"),await this.getOrInitRedirectPersistenceManager(),this.redirectUser&&this.redirectUser._redirectEventId===r._redirectEventId?this.directlySetCurrentUser(r):this.reloadAndSetCurrentUserOrClear(r)}async tryRedirectSignIn(e){let n=null;try{n=await this._popupRedirectResolver._completeRedirectFn(this,e,!0)}catch{await this._setRedirectUser(null)}return n}async reloadAndSetCurrentUserOrClear(e){try{await Xo(e)}catch(n){if((n==null?void 0:n.code)!=="auth/network-request-failed")return this.directlySetCurrentUser(null)}return this.directlySetCurrentUser(e)}useDeviceLanguage(){this.languageCode=Dw()}async _delete(){this._deleted=!0}async updateCurrentUser(e){if(It(this.app))return Promise.reject(Qn(this));const n=e?Yr(e):null;return n&&V(n.auth.config.apiKey===this.config.apiKey,this,"invalid-user-token"),this._updateCurrentUser(n&&n._clone(this))}async _updateCurrentUser(e,n=!1){if(!this._deleted)return e&&V(this.tenantId===e.tenantId,this,"tenant-id-mismatch"),n||await this.beforeStateQueue.runMiddleware(e),this.queue(async()=>{await this.directlySetCurrentUser(e),this.notifyAuthListeners()})}async signOut(){return It(this.app)?Promise.reject(Qn(this)):(await this.beforeStateQueue.runMiddleware(null),(this.redirectPersistenceManager||this._popupRedirectResolver)&&await this._setRedirectUser(null),this._updateCurrentUser(null,!0))}setPersistence(e){return It(this.app)?Promise.reject(Qn(this)):this.queue(async()=>{await this.assertedPersistence.setPersistence(Vt(e))})}_getRecaptchaConfig(){return this.tenantId==null?this._agentRecaptchaConfig:this._tenantRecaptchaConfigs[this.tenantId]}async validatePassword(e){this._getPasswordPolicyInternal()||await this._updatePasswordPolicy();const n=this._getPasswordPolicyInternal();return n.schemaVersion!==this.EXPECTED_PASSWORD_POLICY_SCHEMA_VERSION?Promise.reject(this._errorFactory.create("unsupported-password-policy-schema-version",{})):n.validatePassword(e)}_getPasswordPolicyInternal(){return this.tenantId===null?this._projectPasswordPolicy:this._tenantPasswordPolicies[this.tenantId]}async _updatePasswordPolicy(){const e=await Qw(this),n=new Zw(e);this.tenantId===null?this._projectPasswordPolicy=n:this._tenantPasswordPolicies[this.tenantId]=n}_getPersistenceType(){return this.assertedPersistence.persistence.type}_getPersistence(){return this.assertedPersistence.persistence}_updateErrorMap(e){this._errorFactory=new Ss("auth","Firebase",e())}onAuthStateChanged(e,n,r){return this.registerStateListener(this.authStateSubscription,e,n,r)}beforeAuthStateChanged(e,n){return this.beforeStateQueue.pushCallback(e,n)}onIdTokenChanged(e,n,r){return this.registerStateListener(this.idTokenSubscription,e,n,r)}authStateReady(){return new Promise((e,n)=>{if(this.currentUser)e();else{const r=this.onAuthStateChanged(()=>{r(),e()},n)}})}async revokeAccessToken(e){if(this.currentUser){const n=await this.currentUser.getIdToken(),r={providerId:"apple.com",tokenType:"ACCESS_TOKEN",token:e,idToken:n};this.tenantId!=null&&(r.tenantId=this.tenantId),await Kw(this,r)}}toJSON(){var e;return{apiKey:this.config.apiKey,authDomain:this.config.authDomain,appName:this.name,currentUser:(e=this._currentUser)==null?void 0:e.toJSON()}}async _setRedirectUser(e,n){const r=await this.getOrInitRedirectPersistenceManager(n);return e===null?r.removeCurrentUser():r.setCurrentUser(e)}async getOrInitRedirectPersistenceManager(e){if(!this.redirectPersistenceManager){const n=e&&Vt(e)||this._popupRedirectResolver;V(n,this,"argument-error"),this.redirectPersistenceManager=await Ur.create(this,[Vt(n._redirectPersistence)],"redirectUser"),this.redirectUser=await this.redirectPersistenceManager.getCurrentUser()}return this.redirectPersistenceManager}async _redirectUserForId(e){var n,r;return this._isInitialized&&await this.queue(async()=>{}),((n=this._currentUser)==null?void 0:n._redirectEventId)===e?this._currentUser:((r=this.redirectUser)==null?void 0:r._redirectEventId)===e?this.redirectUser:null}async _persistUserIfCurrent(e){if(e===this.currentUser)return this.queue(async()=>this.directlySetCurrentUser(e))}_notifyListenersIfCurrent(e){e===this.currentUser&&this.notifyAuthListeners()}_key(){return`${this.config.authDomain}:${this.config.apiKey}:${this.name}`}_startProactiveRefresh(){this.isProactiveRefreshEnabled=!0,this.currentUser&&this._currentUser._startProactiveRefresh()}_stopProactiveRefresh(){this.isProactiveRefreshEnabled=!1,this.currentUser&&this._currentUser._stopProactiveRefresh()}get _currentUser(){return this.currentUser}notifyAuthListeners(){var n;if(!this._isInitialized)return;this.idTokenSubscription.next(this.currentUser);const e=((n=this.currentUser)==null?void 0:n.uid)??null;this.lastNotifiedUid!==e&&(this.lastNotifiedUid=e,this.authStateSubscription.next(this.currentUser))}registerStateListener(e,n,r,i){if(this._deleted)return()=>{};const o=typeof n=="function"?n:n.next.bind(n);let l=!1;const u=this._isInitialized?Promise.resolve():this._initializationPromise;if(V(u,this,"internal-error"),u.then(()=>{l||o(this.currentUser)}),typeof n=="function"){const h=e.addObserver(n,r,i);return()=>{l=!0,h()}}else{const h=e.addObserver(n);return()=>{l=!0,h()}}}async directlySetCurrentUser(e){this.currentUser&&this.currentUser!==e&&this._currentUser._stopProactiveRefresh(),e&&this.isProactiveRefreshEnabled&&e._startProactiveRefresh(),this.currentUser=e,e?await this.assertedPersistence.setCurrentUser(e):await this.assertedPersistence.removeCurrentUser()}queue(e){return this.operations=this.operations.then(e,e),this.operations}get assertedPersistence(){return V(this.persistenceManager,this,"internal-error"),this.persistenceManager}_logFramework(e){!e||this.frameworks.includes(e)||(this.frameworks.push(e),this.frameworks.sort(),this.clientVersion=jm(this.config.clientPlatform,this._getFrameworks()))}_getFrameworks(){return this.frameworks}async _getAdditionalHeaders(){var i;const e={"X-Client-Version":this.clientVersion};this.app.options.appId&&(e["X-Firebase-gmpid"]=this.app.options.appId);const n=await((i=this.heartbeatServiceProvider.getImmediate({optional:!0}))==null?void 0:i.getHeartbeatsHeader());n&&(e["X-Firebase-Client"]=n);const r=await this._getAppCheckToken();return r&&(e["X-Firebase-AppCheck"]=r),e}async _getAppCheckToken(){var n;if(It(this.app)&&this.app.settings.appCheckToken)return this.app.settings.appCheckToken;const e=await((n=this.appCheckServiceProvider.getImmediate({optional:!0}))==null?void 0:n.getToken());return e!=null&&e.error&&Rw(`Error while retrieving App Check token: ${e.error}`),e==null?void 0:e.token}}function vl(t){return Yr(t)}class gd{constructor(e){this.auth=e,this.observer=null,this.addObserver=y1(n=>this.observer=n)}get next(){return V(this.observer,this.auth,"internal-error"),this.observer.next.bind(this.observer)}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */let _l={async loadJS(){throw new Error("Unable to load external scripts")},recaptchaV2Script:"",recaptchaEnterpriseScript:"",gapiScript:""};function tE(t){_l=t}function Vm(t){return _l.loadJS(t)}function nE(){return _l.recaptchaEnterpriseScript}function rE(){return _l.gapiScript}function iE(t){return`__${t}${Math.floor(Math.random()*1e6)}`}class sE{constructor(){this.enterprise=new oE}ready(e){e()}execute(e,n){return Promise.resolve("token")}render(e,n){return""}}class oE{ready(e){e()}execute(e,n){return Promise.resolve("token")}render(e,n){return""}}const lE="recaptcha-enterprise",zm="NO_RECAPTCHA";class aE{constructor(e){this.type=lE,this.auth=vl(e)}async verify(e="verify",n=!1){async function r(o){if(!n){if(o.tenantId==null&&o._agentRecaptchaConfig!=null)return o._agentRecaptchaConfig.siteKey;if(o.tenantId!=null&&o._tenantRecaptchaConfigs[o.tenantId]!==void 0)return o._tenantRecaptchaConfigs[o.tenantId].siteKey}return new Promise(async(l,u)=>{Vw(o,{clientType:"CLIENT_TYPE_WEB",version:"RECAPTCHA_ENTERPRISE"}).then(h=>{if(h.recaptchaKey===void 0)u(new Error("recaptcha Enterprise site key undefined"));else{const d=new jw(h);return o.tenantId==null?o._agentRecaptchaConfig=d:o._tenantRecaptchaConfigs[o.tenantId]=d,l(d.siteKey)}}).catch(h=>{u(h)})})}function i(o,l,u){const h=window.grecaptcha;cd(h)?h.enterprise.ready(()=>{h.enterprise.execute(o,{action:e}).then(d=>{l(d)}).catch(()=>{l(zm)})}):u(Error("No reCAPTCHA enterprise script loaded."))}return this.auth.settings.appVerificationDisabledForTesting?new sE().execute("siteKey",{action:"verify"}):new Promise((o,l)=>{r(this.auth).then(u=>{if(!n&&cd(window.grecaptcha))i(u,o,l);else{if(typeof window>"u"){l(new Error("RecaptchaVerifier is only supported in browser"));return}let h=nE();h.length!==0&&(h+=u),Vm(h).then(()=>{i(u,o,l)}).catch(d=>{l(d)})}}).catch(u=>{l(u)})})}}async function md(t,e,n,r=!1,i=!1){const o=new aE(t);let l;if(i)l=zm;else try{l=await o.verify(n)}catch{l=await o.verify(n,!0)}const u={...e};if(n==="mfaSmsEnrollment"||n==="mfaSmsSignIn"){if("phoneEnrollmentInfo"in u){const h=u.phoneEnrollmentInfo.phoneNumber,d=u.phoneEnrollmentInfo.recaptchaToken;Object.assign(u,{phoneEnrollmentInfo:{phoneNumber:h,recaptchaToken:d,captchaResponse:l,clientType:"CLIENT_TYPE_WEB",recaptchaVersion:"RECAPTCHA_ENTERPRISE"}})}else if("phoneSignInInfo"in u){const h=u.phoneSignInInfo.recaptchaToken;Object.assign(u,{phoneSignInInfo:{recaptchaToken:h,captchaResponse:l,clientType:"CLIENT_TYPE_WEB",recaptchaVersion:"RECAPTCHA_ENTERPRISE"}})}return u}return r?Object.assign(u,{captchaResp:l}):Object.assign(u,{captchaResponse:l}),Object.assign(u,{clientType:"CLIENT_TYPE_WEB"}),Object.assign(u,{recaptchaVersion:"RECAPTCHA_ENTERPRISE"}),u}async function yd(t,e,n,r,i){var o;if((o=t._getRecaptchaConfig())!=null&&o.isProviderEnabled("EMAIL_PASSWORD_PROVIDER")){const l=await md(t,e,n,n==="getOobCode");return r(t,l)}else return r(t,e).catch(async l=>{if(l.code==="auth/missing-recaptcha-token"){console.log(`${n} is protected by reCAPTCHA Enterprise for this project. Automatically triggering the reCAPTCHA flow and restarting the flow.`);const u=await md(t,e,n,n==="getOobCode");return r(t,u)}else return Promise.reject(l)})}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function uE(t,e){const n=Nc(t,"auth");if(n.isInitialized()){const i=n.getImmediate(),o=n.getOptions();if(sr(o,e??{}))return i;gt(i,"already-initialized")}return n.initialize({options:e})}function cE(t,e){const n=(e==null?void 0:e.persistence)||[],r=(Array.isArray(n)?n:[n]).map(Vt);e!=null&&e.errorMap&&t._updateErrorMap(e.errorMap),t._initializeWithPersistence(r,e==null?void 0:e.popupRedirectResolver)}function hE(t,e,n){const r=vl(t);V(/^https?:\/\//.test(e),r,"invalid-emulator-scheme");const i=!1,o=$m(e),{host:l,port:u}=fE(e),h=u===null?"":`:${u}`,d={url:`${o}//${l}${h}/`},k=Object.freeze({host:l,port:u,protocol:o.replace(":",""),options:Object.freeze({disableWarnings:i})});if(!r._canInitEmulator){V(r.config.emulator&&r.emulatorConfig,r,"emulator-config-failed"),V(sr(d,r.config.emulator)&&sr(k,r.emulatorConfig),r,"emulator-config-failed");return}r.config.emulator=d,r.emulatorConfig=k,r.settings.appVerificationDisabledForTesting=!0,Es(l)?(pm(`${o}//${l}${h}`),gm("Auth",!0)):dE()}function $m(t){const e=t.indexOf(":");return e<0?"":t.substr(0,e+1)}function fE(t){const e=$m(t),n=/(\/\/)?([^?#/]+)/.exec(t.substr(e.length));if(!n)return{host:"",port:null};const r=n[2].split("@").pop()||"",i=/^(\[[^\]]+\])(:|$)/.exec(r);if(i){const o=i[1];return{host:o,port:vd(r.substr(o.length+1))}}else{const[o,l]=r.split(":");return{host:o,port:vd(l)}}}function vd(t){if(!t)return null;const e=Number(t);return isNaN(e)?null:e}function dE(){function t(){const e=document.createElement("p"),n=e.style;e.innerText="Running in emulator mode. Do not use with production credentials.",n.position="fixed",n.width="100%",n.backgroundColor="#ffffff",n.border=".1em solid #000000",n.color="#b50000",n.bottom="0px",n.left="0px",n.margin="0px",n.zIndex="10000",n.textAlign="center",e.classList.add("firebase-emulator-warning"),document.body.appendChild(e)}typeof console<"u"&&typeof console.info=="function"&&console.info("WARNING: You are using the Auth Emulator, which is intended for local testing only.  Do not use with production credentials."),typeof window<"u"&&typeof document<"u"&&(document.readyState==="loading"?window.addEventListener("DOMContentLoaded",t):t())}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Mc{constructor(e,n){this.providerId=e,this.signInMethod=n}toJSON(){return jt("not implemented")}_getIdTokenResponse(e){return jt("not implemented")}_linkToIdToken(e,n){return jt("not implemented")}_getReauthenticationResolver(e){return jt("not implemented")}}async function pE(t,e){return xn(t,"POST","/v1/accounts:signUp",e)}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */async function gE(t,e){return yl(t,"POST","/v1/accounts:signInWithPassword",cr(t,e))}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */async function mE(t,e){return yl(t,"POST","/v1/accounts:signInWithEmailLink",cr(t,e))}async function yE(t,e){return yl(t,"POST","/v1/accounts:signInWithEmailLink",cr(t,e))}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class ps extends Mc{constructor(e,n,r,i=null){super("password",r),this._email=e,this._password=n,this._tenantId=i}static _fromEmailAndPassword(e,n){return new ps(e,n,"password")}static _fromEmailAndCode(e,n,r=null){return new ps(e,n,"emailLink",r)}toJSON(){return{email:this._email,password:this._password,signInMethod:this.signInMethod,tenantId:this._tenantId}}static fromJSON(e){const n=typeof e=="string"?JSON.parse(e):e;if(n!=null&&n.email&&(n!=null&&n.password)){if(n.signInMethod==="password")return this._fromEmailAndPassword(n.email,n.password);if(n.signInMethod==="emailLink")return this._fromEmailAndCode(n.email,n.password,n.tenantId)}return null}async _getIdTokenResponse(e){switch(this.signInMethod){case"password":const n={returnSecureToken:!0,email:this._email,password:this._password,clientType:"CLIENT_TYPE_WEB"};return yd(e,n,"signInWithPassword",gE);case"emailLink":return mE(e,{email:this._email,oobCode:this._password});default:gt(e,"internal-error")}}async _linkToIdToken(e,n){switch(this.signInMethod){case"password":const r={idToken:n,returnSecureToken:!0,email:this._email,password:this._password,clientType:"CLIENT_TYPE_WEB"};return yd(e,r,"signUpPassword",pE);case"emailLink":return yE(e,{idToken:n,email:this._email,oobCode:this._password});default:gt(e,"internal-error")}}_getReauthenticationResolver(e){return this._getIdTokenResponse(e)}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */async function Fr(t,e){return yl(t,"POST","/v1/accounts:signInWithIdp",cr(t,e))}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const vE="http://localhost";class qt extends Mc{constructor(){super(...arguments),this.pendingToken=null}static _fromParams(e){const n=new qt(e.providerId,e.signInMethod);return e.idToken||e.accessToken?(e.idToken&&(n.idToken=e.idToken),e.accessToken&&(n.accessToken=e.accessToken),e.nonce&&!e.pendingToken&&(n.nonce=e.nonce),e.pendingToken&&(n.pendingToken=e.pendingToken)):e.oauthToken&&e.oauthTokenSecret?(n.accessToken=e.oauthToken,n.secret=e.oauthTokenSecret):gt("argument-error"),n}toJSON(){return{idToken:this.idToken,accessToken:this.accessToken,secret:this.secret,nonce:this.nonce,pendingToken:this.pendingToken,providerId:this.providerId,signInMethod:this.signInMethod}}static fromJSON(e){const n=typeof e=="string"?JSON.parse(e):e,{providerId:r,signInMethod:i,...o}=n;if(!r||!i)return null;const l=new qt(r,i);return l.idToken=o.idToken||void 0,l.accessToken=o.accessToken||void 0,l.secret=o.secret,l.nonce=o.nonce,l.pendingToken=o.pendingToken||null,l}_getIdTokenResponse(e){const n=this.buildRequest();return Fr(e,n)}_linkToIdToken(e,n){const r=this.buildRequest();return r.idToken=n,Fr(e,r)}_getReauthenticationResolver(e){const n=this.buildRequest();return n.autoCreate=!1,Fr(e,n)}buildRequest(){const e={requestUri:vE,returnSecureToken:!0};if(this.pendingToken)e.pendingToken=this.pendingToken;else{const n={};this.idToken&&(n.id_token=this.idToken),this.accessToken&&(n.access_token=this.accessToken),this.secret&&(n.oauth_token_secret=this.secret),n.providerId=this.providerId,this.nonce&&!this.pendingToken&&(n.nonce=this.nonce),e.postBody=Is(n)}return e}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function _E(t){switch(t){case"recoverEmail":return"RECOVER_EMAIL";case"resetPassword":return"PASSWORD_RESET";case"signIn":return"EMAIL_SIGNIN";case"verifyEmail":return"VERIFY_EMAIL";case"verifyAndChangeEmail":return"VERIFY_AND_CHANGE_EMAIL";case"revertSecondFactorAddition":return"REVERT_SECOND_FACTOR_ADDITION";default:return null}}function wE(t){const e=Di(Li(t)).link,n=e?Di(Li(e)).deep_link_id:null,r=Di(Li(t)).deep_link_id;return(r?Di(Li(r)).link:null)||r||n||e||t}class Uc{constructor(e){const n=Di(Li(e)),r=n.apiKey??null,i=n.oobCode??null,o=_E(n.mode??null);V(r&&i&&o,"argument-error"),this.apiKey=r,this.operation=o,this.code=i,this.continueUrl=n.continueUrl??null,this.languageCode=n.lang??null,this.tenantId=n.tenantId??null}static parseLink(e){const n=wE(e);try{return new Uc(n)}catch{return null}}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class ei{constructor(){this.providerId=ei.PROVIDER_ID}static credential(e,n){return ps._fromEmailAndPassword(e,n)}static credentialWithLink(e,n){const r=Uc.parseLink(n);return V(r,"argument-error"),ps._fromEmailAndCode(e,r.code,r.tenantId)}}ei.PROVIDER_ID="password";ei.EMAIL_PASSWORD_SIGN_IN_METHOD="password";ei.EMAIL_LINK_SIGN_IN_METHOD="emailLink";/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class bm{constructor(e){this.providerId=e,this.defaultLanguageCode=null,this.customParameters={}}setDefaultLanguage(e){this.defaultLanguageCode=e}setCustomParameters(e){return this.customParameters=e,this}getCustomParameters(){return this.customParameters}}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class ti extends bm{constructor(){super(...arguments),this.scopes=[]}addScope(e){return this.scopes.includes(e)||this.scopes.push(e),this}getScopes(){return[...this.scopes]}}class Wi extends ti{static credentialFromJSON(e){const n=typeof e=="string"?JSON.parse(e):e;return V("providerId"in n&&"signInMethod"in n,"argument-error"),qt._fromParams(n)}credential(e){return this._credential({...e,nonce:e.rawNonce})}_credential(e){return V(e.idToken||e.accessToken,"argument-error"),qt._fromParams({...e,providerId:this.providerId,signInMethod:this.providerId})}static credentialFromResult(e){return Wi.oauthCredentialFromTaggedObject(e)}static credentialFromError(e){return Wi.oauthCredentialFromTaggedObject(e.customData||{})}static oauthCredentialFromTaggedObject({_tokenResponse:e}){if(!e)return null;const{oauthIdToken:n,oauthAccessToken:r,oauthTokenSecret:i,pendingToken:o,nonce:l,providerId:u}=e;if(!r&&!i&&!n&&!o||!u)return null;try{return new Wi(u)._credential({idToken:n,accessToken:r,nonce:l,pendingToken:o})}catch{return null}}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Lt extends ti{constructor(){super("facebook.com")}static credential(e){return qt._fromParams({providerId:Lt.PROVIDER_ID,signInMethod:Lt.FACEBOOK_SIGN_IN_METHOD,accessToken:e})}static credentialFromResult(e){return Lt.credentialFromTaggedObject(e)}static credentialFromError(e){return Lt.credentialFromTaggedObject(e.customData||{})}static credentialFromTaggedObject({_tokenResponse:e}){if(!e||!("oauthAccessToken"in e)||!e.oauthAccessToken)return null;try{return Lt.credential(e.oauthAccessToken)}catch{return null}}}Lt.FACEBOOK_SIGN_IN_METHOD="facebook.com";Lt.PROVIDER_ID="facebook.com";/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class xt extends ti{constructor(){super("google.com"),this.addScope("profile")}static credential(e,n){return qt._fromParams({providerId:xt.PROVIDER_ID,signInMethod:xt.GOOGLE_SIGN_IN_METHOD,idToken:e,accessToken:n})}static credentialFromResult(e){return xt.credentialFromTaggedObject(e)}static credentialFromError(e){return xt.credentialFromTaggedObject(e.customData||{})}static credentialFromTaggedObject({_tokenResponse:e}){if(!e)return null;const{oauthIdToken:n,oauthAccessToken:r}=e;if(!n&&!r)return null;try{return xt.credential(n,r)}catch{return null}}}xt.GOOGLE_SIGN_IN_METHOD="google.com";xt.PROVIDER_ID="google.com";/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class fn extends ti{constructor(){super("github.com")}static credential(e){return qt._fromParams({providerId:fn.PROVIDER_ID,signInMethod:fn.GITHUB_SIGN_IN_METHOD,accessToken:e})}static credentialFromResult(e){return fn.credentialFromTaggedObject(e)}static credentialFromError(e){return fn.credentialFromTaggedObject(e.customData||{})}static credentialFromTaggedObject({_tokenResponse:e}){if(!e||!("oauthAccessToken"in e)||!e.oauthAccessToken)return null;try{return fn.credential(e.oauthAccessToken)}catch{return null}}}fn.GITHUB_SIGN_IN_METHOD="github.com";fn.PROVIDER_ID="github.com";/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class dn extends ti{constructor(){super("twitter.com")}static credential(e,n){return qt._fromParams({providerId:dn.PROVIDER_ID,signInMethod:dn.TWITTER_SIGN_IN_METHOD,oauthToken:e,oauthTokenSecret:n})}static credentialFromResult(e){return dn.credentialFromTaggedObject(e)}static credentialFromError(e){return dn.credentialFromTaggedObject(e.customData||{})}static credentialFromTaggedObject({_tokenResponse:e}){if(!e)return null;const{oauthAccessToken:n,oauthTokenSecret:r}=e;if(!n||!r)return null;try{return dn.credential(n,r)}catch{return null}}}dn.TWITTER_SIGN_IN_METHOD="twitter.com";dn.PROVIDER_ID="twitter.com";/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Kr{constructor(e){this.user=e.user,this.providerId=e.providerId,this._tokenResponse=e._tokenResponse,this.operationType=e.operationType}static async _fromIdTokenResponse(e,n,r,i=!1){const o=await ct._fromIdTokenResponse(e,r,i),l=_d(r);return new Kr({user:o,providerId:l,_tokenResponse:r,operationType:n})}static async _forOperation(e,n,r){await e._updateTokensIfNecessary(r,!0);const i=_d(r);return new Kr({user:e,providerId:i,_tokenResponse:r,operationType:n})}}function _d(t){return t.providerId?t.providerId:"phoneNumber"in t?"phone":null}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Jo extends Jt{constructor(e,n,r,i){super(n.code,n.message),this.operationType=r,this.user=i,Object.setPrototypeOf(this,Jo.prototype),this.customData={appName:e.name,tenantId:e.tenantId??void 0,_serverResponse:n.customData._serverResponse,operationType:r}}static _fromErrorAndOperation(e,n,r,i){return new Jo(e,n,r,i)}}function Bm(t,e,n,r){return(e==="reauthenticate"?n._getReauthenticationResolver(t):n._getIdTokenResponse(t)).catch(o=>{throw o.code==="auth/multi-factor-auth-required"?Jo._fromErrorAndOperation(t,o,e,r):o})}async function EE(t,e,n=!1){const r=await ds(t,e._linkToIdToken(t.auth,await t.getIdToken()),n);return Kr._forOperation(t,"link",r)}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */async function SE(t,e,n=!1){const{auth:r}=t;if(It(r.app))return Promise.reject(Qn(r));const i="reauthenticate";try{const o=await ds(t,Bm(r,i,e,t),n);V(o.idToken,r,"internal-error");const l=Lc(o.idToken);V(l,r,"internal-error");const{sub:u}=l;return V(t.uid===u,r,"user-mismatch"),Kr._forOperation(t,i,o)}catch(o){throw(o==null?void 0:o.code)==="auth/user-not-found"&&gt(r,"user-mismatch"),o}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */async function IE(t,e,n=!1){if(It(t.app))return Promise.reject(Qn(t));const r="signIn",i=await Bm(t,r,e),o=await Kr._fromIdTokenResponse(t,r,i);return n||await t._updateCurrentUser(o.user),o}function TE(t,e,n,r){return Yr(t).onIdTokenChanged(e,n,r)}function kE(t,e,n){return Yr(t).beforeAuthStateChanged(e,n)}const Qo="__sak";/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Hm{constructor(e,n){this.storageRetriever=e,this.type=n}_isAvailable(){try{return this.storage?(this.storage.setItem(Qo,"1"),this.storage.removeItem(Qo),Promise.resolve(!0)):Promise.resolve(!1)}catch{return Promise.resolve(!1)}}_set(e,n){return this.storage.setItem(e,JSON.stringify(n)),Promise.resolve()}_get(e){const n=this.storage.getItem(e);return Promise.resolve(n?JSON.parse(n):null)}_remove(e){return this.storage.removeItem(e),Promise.resolve()}get storage(){return this.storageRetriever()}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const CE=1e3,PE=10;class Wm extends Hm{constructor(){super(()=>window.localStorage,"LOCAL"),this.boundEventHandler=(e,n)=>this.onStorageEvent(e,n),this.listeners={},this.localCache={},this.pollTimer=null,this.fallbackToPolling=Fm(),this._shouldAllowMigration=!0}forAllChangedKeys(e){for(const n of Object.keys(this.listeners)){const r=this.storage.getItem(n),i=this.localCache[n];r!==i&&e(n,i,r)}}onStorageEvent(e,n=!1){if(!e.key){this.forAllChangedKeys((l,u,h)=>{this.notifyListeners(l,h)});return}const r=e.key;n?this.detachListener():this.stopPolling();const i=()=>{const l=this.storage.getItem(r);!n&&this.localCache[r]===l||this.notifyListeners(r,l)},o=this.storage.getItem(r);Xw()&&o!==e.newValue&&e.newValue!==e.oldValue?setTimeout(i,PE):i()}notifyListeners(e,n){this.localCache[e]=n;const r=this.listeners[e];if(r)for(const i of Array.from(r))i(n&&JSON.parse(n))}startPolling(){this.stopPolling(),this.pollTimer=setInterval(()=>{this.forAllChangedKeys((e,n,r)=>{this.onStorageEvent(new StorageEvent("storage",{key:e,oldValue:n,newValue:r}),!0)})},CE)}stopPolling(){this.pollTimer&&(clearInterval(this.pollTimer),this.pollTimer=null)}attachListener(){window.addEventListener("storage",this.boundEventHandler)}detachListener(){window.removeEventListener("storage",this.boundEventHandler)}_addListener(e,n){Object.keys(this.listeners).length===0&&(this.fallbackToPolling?this.startPolling():this.attachListener()),this.listeners[e]||(this.listeners[e]=new Set,this.localCache[e]=this.storage.getItem(e)),this.listeners[e].add(n)}_removeListener(e,n){this.listeners[e]&&(this.listeners[e].delete(n),this.listeners[e].size===0&&delete this.listeners[e]),Object.keys(this.listeners).length===0&&(this.detachListener(),this.stopPolling())}async _set(e,n){await super._set(e,n),this.localCache[e]=JSON.stringify(n)}async _get(e){const n=await super._get(e);return this.localCache[e]=JSON.stringify(n),n}async _remove(e){await super._remove(e),delete this.localCache[e]}}Wm.type="LOCAL";const AE=Wm;/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Gm extends Hm{constructor(){super(()=>window.sessionStorage,"SESSION")}_addListener(e,n){}_removeListener(e,n){}}Gm.type="SESSION";const Km=Gm;/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function RE(t){return Promise.all(t.map(async e=>{try{return{fulfilled:!0,value:await e}}catch(n){return{fulfilled:!1,reason:n}}}))}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class wl{constructor(e){this.eventTarget=e,this.handlersMap={},this.boundEventHandler=this.handleEvent.bind(this)}static _getInstance(e){const n=this.receivers.find(i=>i.isListeningto(e));if(n)return n;const r=new wl(e);return this.receivers.push(r),r}isListeningto(e){return this.eventTarget===e}async handleEvent(e){const n=e,{eventId:r,eventType:i,data:o}=n.data,l=this.handlersMap[i];if(!(l!=null&&l.size))return;n.ports[0].postMessage({status:"ack",eventId:r,eventType:i});const u=Array.from(l).map(async d=>d(n.origin,o)),h=await RE(u);n.ports[0].postMessage({status:"done",eventId:r,eventType:i,response:h})}_subscribe(e,n){Object.keys(this.handlersMap).length===0&&this.eventTarget.addEventListener("message",this.boundEventHandler),this.handlersMap[e]||(this.handlersMap[e]=new Set),this.handlersMap[e].add(n)}_unsubscribe(e,n){this.handlersMap[e]&&n&&this.handlersMap[e].delete(n),(!n||this.handlersMap[e].size===0)&&delete this.handlersMap[e],Object.keys(this.handlersMap).length===0&&this.eventTarget.removeEventListener("message",this.boundEventHandler)}}wl.receivers=[];/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function Fc(t="",e=10){let n="";for(let r=0;r<e;r++)n+=Math.floor(Math.random()*10);return t+n}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class NE{constructor(e){this.target=e,this.handlers=new Set}removeMessageHandler(e){e.messageChannel&&(e.messageChannel.port1.removeEventListener("message",e.onMessage),e.messageChannel.port1.close()),this.handlers.delete(e)}async _send(e,n,r=50){const i=typeof MessageChannel<"u"?new MessageChannel:null;if(!i)throw new Error("connection_unavailable");let o,l;return new Promise((u,h)=>{const d=Fc("",20);i.port1.start();const k=setTimeout(()=>{h(new Error("unsupported_event"))},r);l={messageChannel:i,onMessage(S){const E=S;if(E.data.eventId===d)switch(E.data.status){case"ack":clearTimeout(k),o=setTimeout(()=>{h(new Error("timeout"))},3e3);break;case"done":clearTimeout(o),u(E.data.response);break;default:clearTimeout(k),clearTimeout(o),h(new Error("invalid_response"));break}}},this.handlers.add(l),i.port1.addEventListener("message",l.onMessage),this.target.postMessage({eventType:e,eventId:d,data:n},[i.port2])}).finally(()=>{l&&this.removeMessageHandler(l)})}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function At(){return window}function OE(t){At().location.href=t}/**
 * @license
 * Copyright 2020 Google LLC.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function qm(){return typeof At().WorkerGlobalScope<"u"&&typeof At().importScripts=="function"}async function DE(){if(!(navigator!=null&&navigator.serviceWorker))return null;try{return(await navigator.serviceWorker.ready).active}catch{return null}}function LE(){var t;return((t=navigator==null?void 0:navigator.serviceWorker)==null?void 0:t.controller)||null}function xE(){return qm()?self:null}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Xm="firebaseLocalStorageDb",ME=1,Yo="firebaseLocalStorage",Jm="fbase_key";class ks{constructor(e){this.request=e}toPromise(){return new Promise((e,n)=>{this.request.addEventListener("success",()=>{e(this.request.result)}),this.request.addEventListener("error",()=>{n(this.request.error)})})}}function El(t,e){return t.transaction([Yo],e?"readwrite":"readonly").objectStore(Yo)}function UE(){const t=indexedDB.deleteDatabase(Xm);return new ks(t).toPromise()}function Ou(){const t=indexedDB.open(Xm,ME);return new Promise((e,n)=>{t.addEventListener("error",()=>{n(t.error)}),t.addEventListener("upgradeneeded",()=>{const r=t.result;try{r.createObjectStore(Yo,{keyPath:Jm})}catch(i){n(i)}}),t.addEventListener("success",async()=>{const r=t.result;r.objectStoreNames.contains(Yo)?e(r):(r.close(),await UE(),e(await Ou()))})})}async function wd(t,e,n){const r=El(t,!0).put({[Jm]:e,value:n});return new ks(r).toPromise()}async function FE(t,e){const n=El(t,!1).get(e),r=await new ks(n).toPromise();return r===void 0?null:r.value}function Ed(t,e){const n=El(t,!0).delete(e);return new ks(n).toPromise()}const jE=800,VE=3;class Qm{constructor(){this.type="LOCAL",this._shouldAllowMigration=!0,this.listeners={},this.localCache={},this.pollTimer=null,this.pendingWrites=0,this.receiver=null,this.sender=null,this.serviceWorkerReceiverAvailable=!1,this.activeServiceWorker=null,this._workerInitializationPromise=this.initializeServiceWorkerMessaging().then(()=>{},()=>{})}async _openDb(){return this.db?this.db:(this.db=await Ou(),this.db)}async _withRetries(e){let n=0;for(;;)try{const r=await this._openDb();return await e(r)}catch(r){if(n++>VE)throw r;this.db&&(this.db.close(),this.db=void 0)}}async initializeServiceWorkerMessaging(){return qm()?this.initializeReceiver():this.initializeSender()}async initializeReceiver(){this.receiver=wl._getInstance(xE()),this.receiver._subscribe("keyChanged",async(e,n)=>({keyProcessed:(await this._poll()).includes(n.key)})),this.receiver._subscribe("ping",async(e,n)=>["keyChanged"])}async initializeSender(){var n,r;if(this.activeServiceWorker=await DE(),!this.activeServiceWorker)return;this.sender=new NE(this.activeServiceWorker);const e=await this.sender._send("ping",{},800);e&&(n=e[0])!=null&&n.fulfilled&&(r=e[0])!=null&&r.value.includes("keyChanged")&&(this.serviceWorkerReceiverAvailable=!0)}async notifyServiceWorker(e){if(!(!this.sender||!this.activeServiceWorker||LE()!==this.activeServiceWorker))try{await this.sender._send("keyChanged",{key:e},this.serviceWorkerReceiverAvailable?800:50)}catch{}}async _isAvailable(){try{if(!indexedDB)return!1;const e=await Ou();return await wd(e,Qo,"1"),await Ed(e,Qo),!0}catch{}return!1}async _withPendingWrite(e){this.pendingWrites++;try{await e()}finally{this.pendingWrites--}}async _set(e,n){return this._withPendingWrite(async()=>(await this._withRetries(r=>wd(r,e,n)),this.localCache[e]=n,this.notifyServiceWorker(e)))}async _get(e){const n=await this._withRetries(r=>FE(r,e));return this.localCache[e]=n,n}async _remove(e){return this._withPendingWrite(async()=>(await this._withRetries(n=>Ed(n,e)),delete this.localCache[e],this.notifyServiceWorker(e)))}async _poll(){const e=await this._withRetries(i=>{const o=El(i,!1).getAll();return new ks(o).toPromise()});if(!e)return[];if(this.pendingWrites!==0)return[];const n=[],r=new Set;if(e.length!==0)for(const{fbase_key:i,value:o}of e)r.add(i),JSON.stringify(this.localCache[i])!==JSON.stringify(o)&&(this.notifyListeners(i,o),n.push(i));for(const i of Object.keys(this.localCache))this.localCache[i]&&!r.has(i)&&(this.notifyListeners(i,null),n.push(i));return n}notifyListeners(e,n){this.localCache[e]=n;const r=this.listeners[e];if(r)for(const i of Array.from(r))i(n)}startPolling(){this.stopPolling(),this.pollTimer=setInterval(async()=>this._poll(),jE)}stopPolling(){this.pollTimer&&(clearInterval(this.pollTimer),this.pollTimer=null)}_addListener(e,n){Object.keys(this.listeners).length===0&&this.startPolling(),this.listeners[e]||(this.listeners[e]=new Set,this._get(e)),this.listeners[e].add(n)}_removeListener(e,n){this.listeners[e]&&(this.listeners[e].delete(n),this.listeners[e].size===0&&delete this.listeners[e]),Object.keys(this.listeners).length===0&&this.stopPolling()}}Qm.type="LOCAL";const zE=Qm;new Ts(3e4,6e4);/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function $E(t,e){return e?Vt(e):(V(t._popupRedirectResolver,t,"argument-error"),t._popupRedirectResolver)}/**
 * @license
 * Copyright 2019 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class jc extends Mc{constructor(e){super("custom","custom"),this.params=e}_getIdTokenResponse(e){return Fr(e,this._buildIdpRequest())}_linkToIdToken(e,n){return Fr(e,this._buildIdpRequest(n))}_getReauthenticationResolver(e){return Fr(e,this._buildIdpRequest())}_buildIdpRequest(e){const n={requestUri:this.params.requestUri,sessionId:this.params.sessionId,postBody:this.params.postBody,tenantId:this.params.tenantId,pendingToken:this.params.pendingToken,returnSecureToken:!0,returnIdpCredential:!0};return e&&(n.idToken=e),n}}function bE(t){return IE(t.auth,new jc(t),t.bypassAuthState)}function BE(t){const{auth:e,user:n}=t;return V(n,e,"internal-error"),SE(n,new jc(t),t.bypassAuthState)}async function HE(t){const{auth:e,user:n}=t;return V(n,e,"internal-error"),EE(n,new jc(t),t.bypassAuthState)}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Ym{constructor(e,n,r,i,o=!1){this.auth=e,this.resolver=r,this.user=i,this.bypassAuthState=o,this.pendingPromise=null,this.eventManager=null,this.filter=Array.isArray(n)?n:[n]}execute(){return new Promise(async(e,n)=>{this.pendingPromise={resolve:e,reject:n};try{this.eventManager=await this.resolver._initialize(this.auth),await this.onExecution(),this.eventManager.registerConsumer(this)}catch(r){this.reject(r)}})}async onAuthEvent(e){const{urlResponse:n,sessionId:r,postBody:i,tenantId:o,error:l,type:u}=e;if(l){this.reject(l);return}const h={auth:this.auth,requestUri:n,sessionId:r,tenantId:o||void 0,postBody:i||void 0,user:this.user,bypassAuthState:this.bypassAuthState};try{this.resolve(await this.getIdpTask(u)(h))}catch(d){this.reject(d)}}onError(e){this.reject(e)}getIdpTask(e){switch(e){case"signInViaPopup":case"signInViaRedirect":return bE;case"linkViaPopup":case"linkViaRedirect":return HE;case"reauthViaPopup":case"reauthViaRedirect":return BE;default:gt(this.auth,"internal-error")}}resolve(e){Kt(this.pendingPromise,"Pending promise was never set"),this.pendingPromise.resolve(e),this.unregisterAndCleanUp()}reject(e){Kt(this.pendingPromise,"Pending promise was never set"),this.pendingPromise.reject(e),this.unregisterAndCleanUp()}unregisterAndCleanUp(){this.eventManager&&this.eventManager.unregisterConsumer(this),this.pendingPromise=null,this.cleanUp()}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const WE=new Ts(2e3,1e4);class Ar extends Ym{constructor(e,n,r,i,o){super(e,n,i,o),this.provider=r,this.authWindow=null,this.pollId=null,Ar.currentPopupAction&&Ar.currentPopupAction.cancel(),Ar.currentPopupAction=this}async executeNotNull(){const e=await this.execute();return V(e,this.auth,"internal-error"),e}async onExecution(){Kt(this.filter.length===1,"Popup operations only handle one event");const e=Fc();this.authWindow=await this.resolver._openPopup(this.auth,this.provider,this.filter[0],e),this.authWindow.associatedEvent=e,this.resolver._originValidation(this.auth).catch(n=>{this.reject(n)}),this.resolver._isIframeWebStorageSupported(this.auth,n=>{n||this.reject(Pt(this.auth,"web-storage-unsupported"))}),this.pollUserCancellation()}get eventId(){var e;return((e=this.authWindow)==null?void 0:e.associatedEvent)||null}cancel(){this.reject(Pt(this.auth,"cancelled-popup-request"))}cleanUp(){this.authWindow&&this.authWindow.close(),this.pollId&&window.clearTimeout(this.pollId),this.authWindow=null,this.pollId=null,Ar.currentPopupAction=null}pollUserCancellation(){const e=()=>{var n,r;if((r=(n=this.authWindow)==null?void 0:n.window)!=null&&r.closed){this.pollId=window.setTimeout(()=>{this.pollId=null,this.reject(Pt(this.auth,"popup-closed-by-user"))},8e3);return}this.pollId=window.setTimeout(e,WE.get())};e()}}Ar.currentPopupAction=null;/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const GE="pendingRedirect",vo=new Map;class KE extends Ym{constructor(e,n,r=!1){super(e,["signInViaRedirect","linkViaRedirect","reauthViaRedirect","unknown"],n,void 0,r),this.eventId=null}async execute(){let e=vo.get(this.auth._key());if(!e){try{const r=await qE(this.resolver,this.auth)?await super.execute():null;e=()=>Promise.resolve(r)}catch(n){e=()=>Promise.reject(n)}vo.set(this.auth._key(),e)}return this.bypassAuthState||vo.set(this.auth._key(),()=>Promise.resolve(null)),e()}async onAuthEvent(e){if(e.type==="signInViaRedirect")return super.onAuthEvent(e);if(e.type==="unknown"){this.resolve(null);return}if(e.eventId){const n=await this.auth._redirectUserForId(e.eventId);if(n)return this.user=n,super.onAuthEvent(e);this.resolve(null)}}async onExecution(){}cleanUp(){}}async function qE(t,e){const n=QE(e),r=JE(t);if(!await r._isAvailable())return!1;const i=await r._get(n)==="true";return await r._remove(n),i}function XE(t,e){vo.set(t._key(),e)}function JE(t){return Vt(t._redirectPersistence)}function QE(t){return yo(GE,t.config.apiKey,t.name)}async function YE(t,e,n=!1){if(It(t.app))return Promise.reject(Qn(t));const r=vl(t),i=$E(r,e),l=await new KE(r,i,n).execute();return l&&!n&&(delete l.user._redirectEventId,await r._persistUserIfCurrent(l.user),await r._setRedirectUser(null,e)),l}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const ZE=10*60*1e3;class eS{constructor(e){this.auth=e,this.cachedEventUids=new Set,this.consumers=new Set,this.queuedRedirectEvent=null,this.hasHandledPotentialRedirect=!1,this.lastProcessedEventTime=Date.now()}registerConsumer(e){this.consumers.add(e),this.queuedRedirectEvent&&this.isEventForConsumer(this.queuedRedirectEvent,e)&&(this.sendToConsumer(this.queuedRedirectEvent,e),this.saveEventToCache(this.queuedRedirectEvent),this.queuedRedirectEvent=null)}unregisterConsumer(e){this.consumers.delete(e)}onEvent(e){if(this.hasEventBeenHandled(e))return!1;let n=!1;return this.consumers.forEach(r=>{this.isEventForConsumer(e,r)&&(n=!0,this.sendToConsumer(e,r),this.saveEventToCache(e))}),this.hasHandledPotentialRedirect||!tS(e)||(this.hasHandledPotentialRedirect=!0,n||(this.queuedRedirectEvent=e,n=!0)),n}sendToConsumer(e,n){var r;if(e.error&&!Zm(e)){const i=((r=e.error.code)==null?void 0:r.split("auth/")[1])||"internal-error";n.onError(Pt(this.auth,i))}else n.onAuthEvent(e)}isEventForConsumer(e,n){const r=n.eventId===null||!!e.eventId&&e.eventId===n.eventId;return n.filter.includes(e.type)&&r}hasEventBeenHandled(e){return Date.now()-this.lastProcessedEventTime>=ZE&&this.cachedEventUids.clear(),this.cachedEventUids.has(Sd(e))}saveEventToCache(e){this.cachedEventUids.add(Sd(e)),this.lastProcessedEventTime=Date.now()}}function Sd(t){return[t.type,t.eventId,t.sessionId,t.tenantId].filter(e=>e).join("-")}function Zm({type:t,error:e}){return t==="unknown"&&(e==null?void 0:e.code)==="auth/no-auth-event"}function tS(t){switch(t.type){case"signInViaRedirect":case"linkViaRedirect":case"reauthViaRedirect":return!0;case"unknown":return Zm(t);default:return!1}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */async function nS(t,e={}){return xn(t,"GET","/v1/projects",e)}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const rS=/^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$/,iS=/^https?/;async function sS(t){if(t.config.emulator)return;const{authorizedDomains:e}=await nS(t);for(const n of e)try{if(oS(n))return}catch{}gt(t,"unauthorized-domain")}function oS(t){const e=Ru(),{protocol:n,hostname:r}=new URL(e);if(t.startsWith("chrome-extension://")){const l=new URL(t);return l.hostname===""&&r===""?n==="chrome-extension:"&&t.replace("chrome-extension://","")===e.replace("chrome-extension://",""):n==="chrome-extension:"&&l.hostname===r}if(!iS.test(n))return!1;if(rS.test(t))return r===t;const i=t.replace(/\./g,"\\.");return new RegExp("^(.+\\."+i+"|"+i+")$","i").test(r)}/**
 * @license
 * Copyright 2020 Google LLC.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const lS=new Ts(3e4,6e4);function Id(){const t=At().___jsl;if(t!=null&&t.H){for(const e of Object.keys(t.H))if(t.H[e].r=t.H[e].r||[],t.H[e].L=t.H[e].L||[],t.H[e].r=[...t.H[e].L],t.CP)for(let n=0;n<t.CP.length;n++)t.CP[n]=null}}function aS(t){return new Promise((e,n)=>{var i,o,l;function r(){Id(),gapi.load("gapi.iframes",{callback:()=>{e(gapi.iframes.getContext())},ontimeout:()=>{Id(),n(Pt(t,"network-request-failed"))},timeout:lS.get()})}if((o=(i=At().gapi)==null?void 0:i.iframes)!=null&&o.Iframe)e(gapi.iframes.getContext());else if((l=At().gapi)!=null&&l.load)r();else{const u=iE("iframefcb");return At()[u]=()=>{gapi.load?r():n(Pt(t,"network-request-failed"))},Vm(`${rE()}?onload=${u}`).catch(h=>n(h))}}).catch(e=>{throw _o=null,e})}let _o=null;function uS(t){return _o=_o||aS(t),_o}/**
 * @license
 * Copyright 2020 Google LLC.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const cS=new Ts(5e3,15e3),hS="__/auth/iframe",fS="emulator/auth/iframe",dS={style:{position:"absolute",top:"-100px",width:"1px",height:"1px"},"aria-hidden":"true",tabindex:"-1"},pS=new Map([["identitytoolkit.googleapis.com","p"],["staging-identitytoolkit.sandbox.googleapis.com","s"],["test-identitytoolkit.sandbox.googleapis.com","t"]]);function gS(t){const e=t.config;V(e.authDomain,t,"auth-domain-config-required");const n=e.emulator?Dc(e,fS):`https://${t.config.authDomain}/${hS}`,r={apiKey:e.apiKey,appName:t.name,v:Zr},i=pS.get(t.config.apiHost);i&&(r.eid=i);const o=t._getFrameworks();return o.length&&(r.fw=o.join(",")),`${n}?${Is(r).slice(1)}`}async function mS(t){const e=await uS(t),n=At().gapi;return V(n,t,"internal-error"),e.open({where:document.body,url:gS(t),messageHandlersFilter:n.iframes.CROSS_ORIGIN_IFRAMES_FILTER,attributes:dS,dontclear:!0},r=>new Promise(async(i,o)=>{await r.restyle({setHideOnLeave:!1});const l=Pt(t,"network-request-failed"),u=At().setTimeout(()=>{o(l)},cS.get());function h(){At().clearTimeout(u),i(r)}r.ping(h).then(h,()=>{o(l)})}))}/**
 * @license
 * Copyright 2020 Google LLC.
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const yS={location:"yes",resizable:"yes",statusbar:"yes",toolbar:"no"},vS=500,_S=600,wS="_blank",ES="http://localhost";class Td{constructor(e){this.window=e,this.associatedEvent=null}close(){if(this.window)try{this.window.close()}catch{}}}function SS(t,e,n,r=vS,i=_S){const o=Math.max((window.screen.availHeight-i)/2,0).toString(),l=Math.max((window.screen.availWidth-r)/2,0).toString();let u="";const h={...yS,width:r.toString(),height:i.toString(),top:o,left:l},d=Me().toLowerCase();n&&(u=Dm(d)?wS:n),Nm(d)&&(e=e||ES,h.scrollbars="yes");const k=Object.entries(h).reduce((E,[N,O])=>`${E}${N}=${O},`,"");if(qw(d)&&u!=="_self")return IS(e||"",u),new Td(null);const S=window.open(e||"",u,k);V(S,t,"popup-blocked");try{S.focus()}catch{}return new Td(S)}function IS(t,e){const n=document.createElement("a");n.href=t,n.target=e;const r=document.createEvent("MouseEvent");r.initMouseEvent("click",!0,!0,window,1,0,0,0,0,!1,!1,!1,!1,1,null),n.dispatchEvent(r)}/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const TS="__/auth/handler",kS="emulator/auth/handler",CS=encodeURIComponent("fac");async function kd(t,e,n,r,i,o){V(t.config.authDomain,t,"auth-domain-config-required"),V(t.config.apiKey,t,"invalid-api-key");const l={apiKey:t.config.apiKey,appName:t.name,authType:n,redirectUrl:r,v:Zr,eventId:i};if(e instanceof bm){e.setDefaultLanguage(t.languageCode),l.providerId=e.providerId||"",m1(e.getCustomParameters())||(l.customParameters=JSON.stringify(e.getCustomParameters()));for(const[k,S]of Object.entries({}))l[k]=S}if(e instanceof ti){const k=e.getScopes().filter(S=>S!=="");k.length>0&&(l.scopes=k.join(","))}t.tenantId&&(l.tid=t.tenantId);const u=l;for(const k of Object.keys(u))u[k]===void 0&&delete u[k];const h=await t._getAppCheckToken(),d=h?`#${CS}=${encodeURIComponent(h)}`:"";return`${PS(t)}?${Is(u).slice(1)}${d}`}function PS({config:t}){return t.emulator?Dc(t,kS):`https://${t.authDomain}/${TS}`}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Ia="webStorageSupport";class AS{constructor(){this.eventManagers={},this.iframes={},this.originValidationPromises={},this._redirectPersistence=Km,this._completeRedirectFn=YE,this._overrideRedirectResult=XE}async _openPopup(e,n,r,i){var l;Kt((l=this.eventManagers[e._key()])==null?void 0:l.manager,"_initialize() not called before _openPopup()");const o=await kd(e,n,r,Ru(),i);return SS(e,o,Fc())}async _openRedirect(e,n,r,i){await this._originValidation(e);const o=await kd(e,n,r,Ru(),i);return OE(o),new Promise(()=>{})}_initialize(e){const n=e._key();if(this.eventManagers[n]){const{manager:i,promise:o}=this.eventManagers[n];return i?Promise.resolve(i):(Kt(o,"If manager is not set, promise should be"),o)}const r=this.initAndGetManager(e);return this.eventManagers[n]={promise:r},r.catch(()=>{delete this.eventManagers[n]}),r}async initAndGetManager(e){const n=await mS(e),r=new eS(e);return n.register("authEvent",i=>(V(i==null?void 0:i.authEvent,e,"invalid-auth-event"),{status:r.onEvent(i.authEvent)?"ACK":"ERROR"}),gapi.iframes.CROSS_ORIGIN_IFRAMES_FILTER),this.eventManagers[e._key()]={manager:r},this.iframes[e._key()]=n,r}_isIframeWebStorageSupported(e,n){this.iframes[e._key()].send(Ia,{type:Ia},i=>{var l;const o=(l=i==null?void 0:i[0])==null?void 0:l[Ia];o!==void 0&&n(!!o),gt(e,"internal-error")},gapi.iframes.CROSS_ORIGIN_IFRAMES_FILTER)}_originValidation(e){const n=e._key();return this.originValidationPromises[n]||(this.originValidationPromises[n]=sS(e)),this.originValidationPromises[n]}get _shouldInitProactively(){return Fm()||Om()||xc()}}const RS=AS;var Cd="@firebase/auth",Pd="1.11.1";/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class NS{constructor(e){this.auth=e,this.internalListeners=new Map}getUid(){var e;return this.assertAuthConfigured(),((e=this.auth.currentUser)==null?void 0:e.uid)||null}async getToken(e){return this.assertAuthConfigured(),await this.auth._initializationPromise,this.auth.currentUser?{accessToken:await this.auth.currentUser.getIdToken(e)}:null}addAuthTokenListener(e){if(this.assertAuthConfigured(),this.internalListeners.has(e))return;const n=this.auth.onIdTokenChanged(r=>{e((r==null?void 0:r.stsTokenManager.accessToken)||null)});this.internalListeners.set(e,n),this.updateProactiveRefresh()}removeAuthTokenListener(e){this.assertAuthConfigured();const n=this.internalListeners.get(e);n&&(this.internalListeners.delete(e),n(),this.updateProactiveRefresh())}assertAuthConfigured(){V(this.auth._initializationPromise,"dependent-sdk-initialized-before-auth")}updateProactiveRefresh(){this.internalListeners.size>0?this.auth._startProactiveRefresh():this.auth._stopProactiveRefresh()}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function OS(t){switch(t){case"Node":return"node";case"ReactNative":return"rn";case"Worker":return"webworker";case"Cordova":return"cordova";case"WebExtension":return"web-extension";default:return}}function DS(t){Gr(new or("auth",(e,{options:n})=>{const r=e.getProvider("app").getImmediate(),i=e.getProvider("heartbeat"),o=e.getProvider("app-check-internal"),{apiKey:l,authDomain:u}=r.options;V(l&&!l.includes(":"),"invalid-api-key",{appName:r.name});const h={apiKey:l,authDomain:u,clientPlatform:t,apiHost:"identitytoolkit.googleapis.com",tokenApiHost:"securetoken.googleapis.com",apiScheme:"https",sdkClientVersion:jm(t)},d=new eE(r,i,o,h);return cE(d,n),d},"PUBLIC").setInstantiationMode("EXPLICIT").setInstanceCreatedCallback((e,n,r)=>{e.getProvider("auth-internal").initialize()})),Gr(new or("auth-internal",e=>{const n=vl(e.getProvider("auth").getImmediate());return(r=>new NS(r))(n)},"PRIVATE").setInstantiationMode("EXPLICIT")),Cn(Cd,Pd,OS(t)),Cn(Cd,Pd,"esm2020")}/**
 * @license
 * Copyright 2021 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const LS=5*60,xS=dm("authIdTokenMaxAge")||LS;let Ad=null;const MS=t=>async e=>{const n=e&&await e.getIdTokenResult(),r=n&&(new Date().getTime()-Date.parse(n.issuedAtTime))/1e3;if(r&&r>xS)return;const i=n==null?void 0:n.token;Ad!==i&&(Ad=i,await fetch(t,{method:i?"POST":"DELETE",headers:i?{Authorization:`Bearer ${i}`}:{}}))};function US(t=_m()){const e=Nc(t,"auth");if(e.isInitialized())return e.getImmediate();const n=uE(t,{popupRedirectResolver:RS,persistence:[zE,AE,Km]}),r=dm("authTokenSyncURL");if(r&&typeof isSecureContext=="boolean"&&isSecureContext){const o=new URL(r,location.origin);if(location.origin===o.origin){const l=MS(o.toString());kE(n,l,()=>l(n.currentUser)),TE(n,u=>l(u))}}const i=hm("auth");return i&&hE(n,`http://${i}`),n}function FS(){var t;return((t=document.getElementsByTagName("head"))==null?void 0:t[0])??document}tE({loadJS(t){return new Promise((e,n)=>{const r=document.createElement("script");r.setAttribute("src",t),r.onload=e,r.onerror=i=>{const o=Pt("internal-error");o.customData=i,n(o)},r.type="text/javascript",r.charset="UTF-8",FS().appendChild(r)})},gapiScript:"https://apis.google.com/js/api.js",recaptchaV2Script:"https://www.google.com/recaptcha/api.js",recaptchaEnterpriseScript:"https://www.google.com/recaptcha/enterprise.js?render="});DS("Browser");var jS="firebase",VS="12.5.0";/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */Cn(jS,VS,"app");var Rd=typeof globalThis<"u"?globalThis:typeof window<"u"?window:typeof global<"u"?global:typeof self<"u"?self:{};/** @license
Copyright The Closure Library Authors.
SPDX-License-Identifier: Apache-2.0
*/var Vc;(function(){var t;/** @license

 Copyright The Closure Library Authors.
 SPDX-License-Identifier: Apache-2.0
*/function e(g,p){function m(){}m.prototype=p.prototype,g.F=p.prototype,g.prototype=new m,g.prototype.constructor=g,g.D=function(v,w,C){for(var y=Array(arguments.length-2),we=2;we<arguments.length;we++)y[we-2]=arguments[we];return p.prototype[w].apply(v,y)}}function n(){this.blockSize=-1}function r(){this.blockSize=-1,this.blockSize=64,this.g=Array(4),this.C=Array(this.blockSize),this.o=this.h=0,this.u()}e(r,n),r.prototype.u=function(){this.g[0]=1732584193,this.g[1]=4023233417,this.g[2]=2562383102,this.g[3]=271733878,this.o=this.h=0};function i(g,p,m){m||(m=0);const v=Array(16);if(typeof p=="string")for(var w=0;w<16;++w)v[w]=p.charCodeAt(m++)|p.charCodeAt(m++)<<8|p.charCodeAt(m++)<<16|p.charCodeAt(m++)<<24;else for(w=0;w<16;++w)v[w]=p[m++]|p[m++]<<8|p[m++]<<16|p[m++]<<24;p=g.g[0],m=g.g[1],w=g.g[2];let C=g.g[3],y;y=p+(C^m&(w^C))+v[0]+3614090360&4294967295,p=m+(y<<7&4294967295|y>>>25),y=C+(w^p&(m^w))+v[1]+3905402710&4294967295,C=p+(y<<12&4294967295|y>>>20),y=w+(m^C&(p^m))+v[2]+606105819&4294967295,w=C+(y<<17&4294967295|y>>>15),y=m+(p^w&(C^p))+v[3]+3250441966&4294967295,m=w+(y<<22&4294967295|y>>>10),y=p+(C^m&(w^C))+v[4]+4118548399&4294967295,p=m+(y<<7&4294967295|y>>>25),y=C+(w^p&(m^w))+v[5]+1200080426&4294967295,C=p+(y<<12&4294967295|y>>>20),y=w+(m^C&(p^m))+v[6]+2821735955&4294967295,w=C+(y<<17&4294967295|y>>>15),y=m+(p^w&(C^p))+v[7]+4249261313&4294967295,m=w+(y<<22&4294967295|y>>>10),y=p+(C^m&(w^C))+v[8]+1770035416&4294967295,p=m+(y<<7&4294967295|y>>>25),y=C+(w^p&(m^w))+v[9]+2336552879&4294967295,C=p+(y<<12&4294967295|y>>>20),y=w+(m^C&(p^m))+v[10]+4294925233&4294967295,w=C+(y<<17&4294967295|y>>>15),y=m+(p^w&(C^p))+v[11]+2304563134&4294967295,m=w+(y<<22&4294967295|y>>>10),y=p+(C^m&(w^C))+v[12]+1804603682&4294967295,p=m+(y<<7&4294967295|y>>>25),y=C+(w^p&(m^w))+v[13]+4254626195&4294967295,C=p+(y<<12&4294967295|y>>>20),y=w+(m^C&(p^m))+v[14]+2792965006&4294967295,w=C+(y<<17&4294967295|y>>>15),y=m+(p^w&(C^p))+v[15]+1236535329&4294967295,m=w+(y<<22&4294967295|y>>>10),y=p+(w^C&(m^w))+v[1]+4129170786&4294967295,p=m+(y<<5&4294967295|y>>>27),y=C+(m^w&(p^m))+v[6]+3225465664&4294967295,C=p+(y<<9&4294967295|y>>>23),y=w+(p^m&(C^p))+v[11]+643717713&4294967295,w=C+(y<<14&4294967295|y>>>18),y=m+(C^p&(w^C))+v[0]+3921069994&4294967295,m=w+(y<<20&4294967295|y>>>12),y=p+(w^C&(m^w))+v[5]+3593408605&4294967295,p=m+(y<<5&4294967295|y>>>27),y=C+(m^w&(p^m))+v[10]+38016083&4294967295,C=p+(y<<9&4294967295|y>>>23),y=w+(p^m&(C^p))+v[15]+3634488961&4294967295,w=C+(y<<14&4294967295|y>>>18),y=m+(C^p&(w^C))+v[4]+3889429448&4294967295,m=w+(y<<20&4294967295|y>>>12),y=p+(w^C&(m^w))+v[9]+568446438&4294967295,p=m+(y<<5&4294967295|y>>>27),y=C+(m^w&(p^m))+v[14]+3275163606&4294967295,C=p+(y<<9&4294967295|y>>>23),y=w+(p^m&(C^p))+v[3]+4107603335&4294967295,w=C+(y<<14&4294967295|y>>>18),y=m+(C^p&(w^C))+v[8]+1163531501&4294967295,m=w+(y<<20&4294967295|y>>>12),y=p+(w^C&(m^w))+v[13]+2850285829&4294967295,p=m+(y<<5&4294967295|y>>>27),y=C+(m^w&(p^m))+v[2]+4243563512&4294967295,C=p+(y<<9&4294967295|y>>>23),y=w+(p^m&(C^p))+v[7]+1735328473&4294967295,w=C+(y<<14&4294967295|y>>>18),y=m+(C^p&(w^C))+v[12]+2368359562&4294967295,m=w+(y<<20&4294967295|y>>>12),y=p+(m^w^C)+v[5]+4294588738&4294967295,p=m+(y<<4&4294967295|y>>>28),y=C+(p^m^w)+v[8]+2272392833&4294967295,C=p+(y<<11&4294967295|y>>>21),y=w+(C^p^m)+v[11]+1839030562&4294967295,w=C+(y<<16&4294967295|y>>>16),y=m+(w^C^p)+v[14]+4259657740&4294967295,m=w+(y<<23&4294967295|y>>>9),y=p+(m^w^C)+v[1]+2763975236&4294967295,p=m+(y<<4&4294967295|y>>>28),y=C+(p^m^w)+v[4]+1272893353&4294967295,C=p+(y<<11&4294967295|y>>>21),y=w+(C^p^m)+v[7]+4139469664&4294967295,w=C+(y<<16&4294967295|y>>>16),y=m+(w^C^p)+v[10]+3200236656&4294967295,m=w+(y<<23&4294967295|y>>>9),y=p+(m^w^C)+v[13]+681279174&4294967295,p=m+(y<<4&4294967295|y>>>28),y=C+(p^m^w)+v[0]+3936430074&4294967295,C=p+(y<<11&4294967295|y>>>21),y=w+(C^p^m)+v[3]+3572445317&4294967295,w=C+(y<<16&4294967295|y>>>16),y=m+(w^C^p)+v[6]+76029189&4294967295,m=w+(y<<23&4294967295|y>>>9),y=p+(m^w^C)+v[9]+3654602809&4294967295,p=m+(y<<4&4294967295|y>>>28),y=C+(p^m^w)+v[12]+3873151461&4294967295,C=p+(y<<11&4294967295|y>>>21),y=w+(C^p^m)+v[15]+530742520&4294967295,w=C+(y<<16&4294967295|y>>>16),y=m+(w^C^p)+v[2]+3299628645&4294967295,m=w+(y<<23&4294967295|y>>>9),y=p+(w^(m|~C))+v[0]+4096336452&4294967295,p=m+(y<<6&4294967295|y>>>26),y=C+(m^(p|~w))+v[7]+1126891415&4294967295,C=p+(y<<10&4294967295|y>>>22),y=w+(p^(C|~m))+v[14]+2878612391&4294967295,w=C+(y<<15&4294967295|y>>>17),y=m+(C^(w|~p))+v[5]+4237533241&4294967295,m=w+(y<<21&4294967295|y>>>11),y=p+(w^(m|~C))+v[12]+1700485571&4294967295,p=m+(y<<6&4294967295|y>>>26),y=C+(m^(p|~w))+v[3]+2399980690&4294967295,C=p+(y<<10&4294967295|y>>>22),y=w+(p^(C|~m))+v[10]+4293915773&4294967295,w=C+(y<<15&4294967295|y>>>17),y=m+(C^(w|~p))+v[1]+2240044497&4294967295,m=w+(y<<21&4294967295|y>>>11),y=p+(w^(m|~C))+v[8]+1873313359&4294967295,p=m+(y<<6&4294967295|y>>>26),y=C+(m^(p|~w))+v[15]+4264355552&4294967295,C=p+(y<<10&4294967295|y>>>22),y=w+(p^(C|~m))+v[6]+2734768916&4294967295,w=C+(y<<15&4294967295|y>>>17),y=m+(C^(w|~p))+v[13]+1309151649&4294967295,m=w+(y<<21&4294967295|y>>>11),y=p+(w^(m|~C))+v[4]+4149444226&4294967295,p=m+(y<<6&4294967295|y>>>26),y=C+(m^(p|~w))+v[11]+3174756917&4294967295,C=p+(y<<10&4294967295|y>>>22),y=w+(p^(C|~m))+v[2]+718787259&4294967295,w=C+(y<<15&4294967295|y>>>17),y=m+(C^(w|~p))+v[9]+3951481745&4294967295,g.g[0]=g.g[0]+p&4294967295,g.g[1]=g.g[1]+(w+(y<<21&4294967295|y>>>11))&4294967295,g.g[2]=g.g[2]+w&4294967295,g.g[3]=g.g[3]+C&4294967295}r.prototype.v=function(g,p){p===void 0&&(p=g.length);const m=p-this.blockSize,v=this.C;let w=this.h,C=0;for(;C<p;){if(w==0)for(;C<=m;)i(this,g,C),C+=this.blockSize;if(typeof g=="string"){for(;C<p;)if(v[w++]=g.charCodeAt(C++),w==this.blockSize){i(this,v),w=0;break}}else for(;C<p;)if(v[w++]=g[C++],w==this.blockSize){i(this,v),w=0;break}}this.h=w,this.o+=p},r.prototype.A=function(){var g=Array((this.h<56?this.blockSize:this.blockSize*2)-this.h);g[0]=128;for(var p=1;p<g.length-8;++p)g[p]=0;p=this.o*8;for(var m=g.length-8;m<g.length;++m)g[m]=p&255,p/=256;for(this.v(g),g=Array(16),p=0,m=0;m<4;++m)for(let v=0;v<32;v+=8)g[p++]=this.g[m]>>>v&255;return g};function o(g,p){var m=u;return Object.prototype.hasOwnProperty.call(m,g)?m[g]:m[g]=p(g)}function l(g,p){this.h=p;const m=[];let v=!0;for(let w=g.length-1;w>=0;w--){const C=g[w]|0;v&&C==p||(m[w]=C,v=!1)}this.g=m}var u={};function h(g){return-128<=g&&g<128?o(g,function(p){return new l([p|0],p<0?-1:0)}):new l([g|0],g<0?-1:0)}function d(g){if(isNaN(g)||!isFinite(g))return S;if(g<0)return z(d(-g));const p=[];let m=1;for(let v=0;g>=m;v++)p[v]=g/m|0,m*=4294967296;return new l(p,0)}function k(g,p){if(g.length==0)throw Error("number format error: empty string");if(p=p||10,p<2||36<p)throw Error("radix out of range: "+p);if(g.charAt(0)=="-")return z(k(g.substring(1),p));if(g.indexOf("-")>=0)throw Error('number format error: interior "-" character');const m=d(Math.pow(p,8));let v=S;for(let C=0;C<g.length;C+=8){var w=Math.min(8,g.length-C);const y=parseInt(g.substring(C,C+w),p);w<8?(w=d(Math.pow(p,w)),v=v.j(w).add(d(y))):(v=v.j(m),v=v.add(d(y)))}return v}var S=h(0),E=h(1),N=h(16777216);t=l.prototype,t.m=function(){if(L(this))return-z(this).m();let g=0,p=1;for(let m=0;m<this.g.length;m++){const v=this.i(m);g+=(v>=0?v:4294967296+v)*p,p*=4294967296}return g},t.toString=function(g){if(g=g||10,g<2||36<g)throw Error("radix out of range: "+g);if(O(this))return"0";if(L(this))return"-"+z(this).toString(g);const p=d(Math.pow(g,6));var m=this;let v="";for(;;){const w=R(m,p).g;m=I(m,w.j(p));let C=((m.g.length>0?m.g[0]:m.h)>>>0).toString(g);if(m=w,O(m))return C+v;for(;C.length<6;)C="0"+C;v=C+v}},t.i=function(g){return g<0?0:g<this.g.length?this.g[g]:this.h};function O(g){if(g.h!=0)return!1;for(let p=0;p<g.g.length;p++)if(g.g[p]!=0)return!1;return!0}function L(g){return g.h==-1}t.l=function(g){return g=I(this,g),L(g)?-1:O(g)?0:1};function z(g){const p=g.g.length,m=[];for(let v=0;v<p;v++)m[v]=~g.g[v];return new l(m,~g.h).add(E)}t.abs=function(){return L(this)?z(this):this},t.add=function(g){const p=Math.max(this.g.length,g.g.length),m=[];let v=0;for(let w=0;w<=p;w++){let C=v+(this.i(w)&65535)+(g.i(w)&65535),y=(C>>>16)+(this.i(w)>>>16)+(g.i(w)>>>16);v=y>>>16,C&=65535,y&=65535,m[w]=y<<16|C}return new l(m,m[m.length-1]&-2147483648?-1:0)};function I(g,p){return g.add(z(p))}t.j=function(g){if(O(this)||O(g))return S;if(L(this))return L(g)?z(this).j(z(g)):z(z(this).j(g));if(L(g))return z(this.j(z(g)));if(this.l(N)<0&&g.l(N)<0)return d(this.m()*g.m());const p=this.g.length+g.g.length,m=[];for(var v=0;v<2*p;v++)m[v]=0;for(v=0;v<this.g.length;v++)for(let w=0;w<g.g.length;w++){const C=this.i(v)>>>16,y=this.i(v)&65535,we=g.i(w)>>>16,Rt=g.i(w)&65535;m[2*v+2*w]+=y*Rt,_(m,2*v+2*w),m[2*v+2*w+1]+=C*Rt,_(m,2*v+2*w+1),m[2*v+2*w+1]+=y*we,_(m,2*v+2*w+1),m[2*v+2*w+2]+=C*we,_(m,2*v+2*w+2)}for(g=0;g<p;g++)m[g]=m[2*g+1]<<16|m[2*g];for(g=p;g<2*p;g++)m[g]=0;return new l(m,0)};function _(g,p){for(;(g[p]&65535)!=g[p];)g[p+1]+=g[p]>>>16,g[p]&=65535,p++}function T(g,p){this.g=g,this.h=p}function R(g,p){if(O(p))throw Error("division by zero");if(O(g))return new T(S,S);if(L(g))return p=R(z(g),p),new T(z(p.g),z(p.h));if(L(p))return p=R(g,z(p)),new T(z(p.g),p.h);if(g.g.length>30){if(L(g)||L(p))throw Error("slowDivide_ only works with positive integers.");for(var m=E,v=p;v.l(g)<=0;)m=M(m),v=M(v);var w=U(m,1),C=U(v,1);for(v=U(v,2),m=U(m,2);!O(v);){var y=C.add(v);y.l(g)<=0&&(w=w.add(m),C=y),v=U(v,1),m=U(m,1)}return p=I(g,w.j(p)),new T(w,p)}for(w=S;g.l(p)>=0;){for(m=Math.max(1,Math.floor(g.m()/p.m())),v=Math.ceil(Math.log(m)/Math.LN2),v=v<=48?1:Math.pow(2,v-48),C=d(m),y=C.j(p);L(y)||y.l(g)>0;)m-=v,C=d(m),y=C.j(p);O(C)&&(C=E),w=w.add(C),g=I(g,y)}return new T(w,g)}t.B=function(g){return R(this,g).h},t.and=function(g){const p=Math.max(this.g.length,g.g.length),m=[];for(let v=0;v<p;v++)m[v]=this.i(v)&g.i(v);return new l(m,this.h&g.h)},t.or=function(g){const p=Math.max(this.g.length,g.g.length),m=[];for(let v=0;v<p;v++)m[v]=this.i(v)|g.i(v);return new l(m,this.h|g.h)},t.xor=function(g){const p=Math.max(this.g.length,g.g.length),m=[];for(let v=0;v<p;v++)m[v]=this.i(v)^g.i(v);return new l(m,this.h^g.h)};function M(g){const p=g.g.length+1,m=[];for(let v=0;v<p;v++)m[v]=g.i(v)<<1|g.i(v-1)>>>31;return new l(m,g.h)}function U(g,p){const m=p>>5;p%=32;const v=g.g.length-m,w=[];for(let C=0;C<v;C++)w[C]=p>0?g.i(C+m)>>>p|g.i(C+m+1)<<32-p:g.i(C+m);return new l(w,g.h)}r.prototype.digest=r.prototype.A,r.prototype.reset=r.prototype.u,r.prototype.update=r.prototype.v,l.prototype.add=l.prototype.add,l.prototype.multiply=l.prototype.j,l.prototype.modulo=l.prototype.B,l.prototype.compare=l.prototype.l,l.prototype.toNumber=l.prototype.m,l.prototype.toString=l.prototype.toString,l.prototype.getBits=l.prototype.i,l.fromNumber=d,l.fromString=k,Vc=l}).apply(typeof Rd<"u"?Rd:typeof self<"u"?self:typeof window<"u"?window:{});var to=typeof globalThis<"u"?globalThis:typeof window<"u"?window:typeof global<"u"?global:typeof self<"u"?self:{};(function(){var t,e=Object.defineProperty;function n(s){s=[typeof globalThis=="object"&&globalThis,s,typeof window=="object"&&window,typeof self=="object"&&self,typeof to=="object"&&to];for(var a=0;a<s.length;++a){var c=s[a];if(c&&c.Math==Math)return c}throw Error("Cannot find global object")}var r=n(this);function i(s,a){if(a)e:{var c=r;s=s.split(".");for(var f=0;f<s.length-1;f++){var P=s[f];if(!(P in c))break e;c=c[P]}s=s[s.length-1],f=c[s],a=a(f),a!=f&&a!=null&&e(c,s,{configurable:!0,writable:!0,value:a})}}i("Symbol.dispose",function(s){return s||Symbol("Symbol.dispose")}),i("Array.prototype.values",function(s){return s||function(){return this[Symbol.iterator]()}}),i("Object.entries",function(s){return s||function(a){var c=[],f;for(f in a)Object.prototype.hasOwnProperty.call(a,f)&&c.push([f,a[f]]);return c}});/** @license

 Copyright The Closure Library Authors.
 SPDX-License-Identifier: Apache-2.0
*/var o=o||{},l=this||self;function u(s){var a=typeof s;return a=="object"&&s!=null||a=="function"}function h(s,a,c){return s.call.apply(s.bind,arguments)}function d(s,a,c){return d=h,d.apply(null,arguments)}function k(s,a){var c=Array.prototype.slice.call(arguments,1);return function(){var f=c.slice();return f.push.apply(f,arguments),s.apply(this,f)}}function S(s,a){function c(){}c.prototype=a.prototype,s.Z=a.prototype,s.prototype=new c,s.prototype.constructor=s,s.Ob=function(f,P,A){for(var x=Array(arguments.length-2),B=2;B<arguments.length;B++)x[B-2]=arguments[B];return a.prototype[P].apply(f,x)}}var E=typeof AsyncContext<"u"&&typeof AsyncContext.Snapshot=="function"?s=>s&&AsyncContext.Snapshot.wrap(s):s=>s;function N(s){const a=s.length;if(a>0){const c=Array(a);for(let f=0;f<a;f++)c[f]=s[f];return c}return[]}function O(s,a){for(let f=1;f<arguments.length;f++){const P=arguments[f];var c=typeof P;if(c=c!="object"?c:P?Array.isArray(P)?"array":c:"null",c=="array"||c=="object"&&typeof P.length=="number"){c=s.length||0;const A=P.length||0;s.length=c+A;for(let x=0;x<A;x++)s[c+x]=P[x]}else s.push(P)}}class L{constructor(a,c){this.i=a,this.j=c,this.h=0,this.g=null}get(){let a;return this.h>0?(this.h--,a=this.g,this.g=a.next,a.next=null):a=this.i(),a}}function z(s){l.setTimeout(()=>{throw s},0)}function I(){var s=g;let a=null;return s.g&&(a=s.g,s.g=s.g.next,s.g||(s.h=null),a.next=null),a}class _{constructor(){this.h=this.g=null}add(a,c){const f=T.get();f.set(a,c),this.h?this.h.next=f:this.g=f,this.h=f}}var T=new L(()=>new R,s=>s.reset());class R{constructor(){this.next=this.g=this.h=null}set(a,c){this.h=a,this.g=c,this.next=null}reset(){this.next=this.g=this.h=null}}let M,U=!1,g=new _,p=()=>{const s=Promise.resolve(void 0);M=()=>{s.then(m)}};function m(){for(var s;s=I();){try{s.h.call(s.g)}catch(c){z(c)}var a=T;a.j(s),a.h<100&&(a.h++,s.next=a.g,a.g=s)}U=!1}function v(){this.u=this.u,this.C=this.C}v.prototype.u=!1,v.prototype.dispose=function(){this.u||(this.u=!0,this.N())},v.prototype[Symbol.dispose]=function(){this.dispose()},v.prototype.N=function(){if(this.C)for(;this.C.length;)this.C.shift()()};function w(s,a){this.type=s,this.g=this.target=a,this.defaultPrevented=!1}w.prototype.h=function(){this.defaultPrevented=!0};var C=function(){if(!l.addEventListener||!Object.defineProperty)return!1;var s=!1,a=Object.defineProperty({},"passive",{get:function(){s=!0}});try{const c=()=>{};l.addEventListener("test",c,a),l.removeEventListener("test",c,a)}catch{}return s}();function y(s){return/^[\s\xa0]*$/.test(s)}function we(s,a){w.call(this,s?s.type:""),this.relatedTarget=this.g=this.target=null,this.button=this.screenY=this.screenX=this.clientY=this.clientX=0,this.key="",this.metaKey=this.shiftKey=this.altKey=this.ctrlKey=!1,this.state=null,this.pointerId=0,this.pointerType="",this.i=null,s&&this.init(s,a)}S(we,w),we.prototype.init=function(s,a){const c=this.type=s.type,f=s.changedTouches&&s.changedTouches.length?s.changedTouches[0]:null;this.target=s.target||s.srcElement,this.g=a,a=s.relatedTarget,a||(c=="mouseover"?a=s.fromElement:c=="mouseout"&&(a=s.toElement)),this.relatedTarget=a,f?(this.clientX=f.clientX!==void 0?f.clientX:f.pageX,this.clientY=f.clientY!==void 0?f.clientY:f.pageY,this.screenX=f.screenX||0,this.screenY=f.screenY||0):(this.clientX=s.clientX!==void 0?s.clientX:s.pageX,this.clientY=s.clientY!==void 0?s.clientY:s.pageY,this.screenX=s.screenX||0,this.screenY=s.screenY||0),this.button=s.button,this.key=s.key||"",this.ctrlKey=s.ctrlKey,this.altKey=s.altKey,this.shiftKey=s.shiftKey,this.metaKey=s.metaKey,this.pointerId=s.pointerId||0,this.pointerType=s.pointerType,this.state=s.state,this.i=s,s.defaultPrevented&&we.Z.h.call(this)},we.prototype.h=function(){we.Z.h.call(this);const s=this.i;s.preventDefault?s.preventDefault():s.returnValue=!1};var Rt="closure_listenable_"+(Math.random()*1e6|0),ni=0;function ri(s,a,c,f,P){this.listener=s,this.proxy=null,this.src=a,this.type=c,this.capture=!!f,this.ha=P,this.key=++ni,this.da=this.fa=!1}function F(s){s.da=!0,s.listener=null,s.proxy=null,s.src=null,s.ha=null}function $(s,a,c){for(const f in s)a.call(c,s[f],f,s)}function b(s,a){for(const c in s)a.call(void 0,s[c],c,s)}function re(s){const a={};for(const c in s)a[c]=s[c];return a}const ue="constructor hasOwnProperty isPrototypeOf propertyIsEnumerable toLocaleString toString valueOf".split(" ");function Mn(s,a){let c,f;for(let P=1;P<arguments.length;P++){f=arguments[P];for(c in f)s[c]=f[c];for(let A=0;A<ue.length;A++)c=ue[A],Object.prototype.hasOwnProperty.call(f,c)&&(s[c]=f[c])}}function Je(s){this.src=s,this.g={},this.h=0}Je.prototype.add=function(s,a,c,f,P){const A=s.toString();s=this.g[A],s||(s=this.g[A]=[],this.h++);const x=it(s,a,f,P);return x>-1?(a=s[x],c||(a.fa=!1)):(a=new ri(a,this.src,A,!!f,P),a.fa=c,s.push(a)),a};function Un(s,a){const c=a.type;if(c in s.g){var f=s.g[c],P=Array.prototype.indexOf.call(f,a,void 0),A;(A=P>=0)&&Array.prototype.splice.call(f,P,1),A&&(F(a),s.g[c].length==0&&(delete s.g[c],s.h--))}}function it(s,a,c,f){for(let P=0;P<s.length;++P){const A=s[P];if(!A.da&&A.listener==a&&A.capture==!!c&&A.ha==f)return P}return-1}var Qt="closure_lm_"+(Math.random()*1e6|0),Sl={};function Hc(s,a,c,f,P){if(Array.isArray(a)){for(let A=0;A<a.length;A++)Hc(s,a[A],c,f,P);return null}return c=Kc(c),s&&s[Rt]?s.J(a,c,u(f)?!!f.capture:!1,P):uy(s,a,c,!1,f,P)}function uy(s,a,c,f,P,A){if(!a)throw Error("Invalid event type");const x=u(P)?!!P.capture:!!P;let B=Tl(s);if(B||(s[Qt]=B=new Je(s)),c=B.add(a,c,f,x,A),c.proxy)return c;if(f=cy(),c.proxy=f,f.src=s,f.listener=c,s.addEventListener)C||(P=x),P===void 0&&(P=!1),s.addEventListener(a.toString(),f,P);else if(s.attachEvent)s.attachEvent(Gc(a.toString()),f);else if(s.addListener&&s.removeListener)s.addListener(f);else throw Error("addEventListener and attachEvent are unavailable.");return c}function cy(){function s(c){return a.call(s.src,s.listener,c)}const a=hy;return s}function Wc(s,a,c,f,P){if(Array.isArray(a))for(var A=0;A<a.length;A++)Wc(s,a[A],c,f,P);else f=u(f)?!!f.capture:!!f,c=Kc(c),s&&s[Rt]?(s=s.i,A=String(a).toString(),A in s.g&&(a=s.g[A],c=it(a,c,f,P),c>-1&&(F(a[c]),Array.prototype.splice.call(a,c,1),a.length==0&&(delete s.g[A],s.h--)))):s&&(s=Tl(s))&&(a=s.g[a.toString()],s=-1,a&&(s=it(a,c,f,P)),(c=s>-1?a[s]:null)&&Il(c))}function Il(s){if(typeof s!="number"&&s&&!s.da){var a=s.src;if(a&&a[Rt])Un(a.i,s);else{var c=s.type,f=s.proxy;a.removeEventListener?a.removeEventListener(c,f,s.capture):a.detachEvent?a.detachEvent(Gc(c),f):a.addListener&&a.removeListener&&a.removeListener(f),(c=Tl(a))?(Un(c,s),c.h==0&&(c.src=null,a[Qt]=null)):F(s)}}}function Gc(s){return s in Sl?Sl[s]:Sl[s]="on"+s}function hy(s,a){if(s.da)s=!0;else{a=new we(a,this);const c=s.listener,f=s.ha||s.src;s.fa&&Il(s),s=c.call(f,a)}return s}function Tl(s){return s=s[Qt],s instanceof Je?s:null}var kl="__closure_events_fn_"+(Math.random()*1e9>>>0);function Kc(s){return typeof s=="function"?s:(s[kl]||(s[kl]=function(a){return s.handleEvent(a)}),s[kl])}function Te(){v.call(this),this.i=new Je(this),this.M=this,this.G=null}S(Te,v),Te.prototype[Rt]=!0,Te.prototype.removeEventListener=function(s,a,c,f){Wc(this,s,a,c,f)};function Ne(s,a){var c,f=s.G;if(f)for(c=[];f;f=f.G)c.push(f);if(s=s.M,f=a.type||a,typeof a=="string")a=new w(a,s);else if(a instanceof w)a.target=a.target||s;else{var P=a;a=new w(f,s),Mn(a,P)}P=!0;let A,x;if(c)for(x=c.length-1;x>=0;x--)A=a.g=c[x],P=As(A,f,!0,a)&&P;if(A=a.g=s,P=As(A,f,!0,a)&&P,P=As(A,f,!1,a)&&P,c)for(x=0;x<c.length;x++)A=a.g=c[x],P=As(A,f,!1,a)&&P}Te.prototype.N=function(){if(Te.Z.N.call(this),this.i){var s=this.i;for(const a in s.g){const c=s.g[a];for(let f=0;f<c.length;f++)F(c[f]);delete s.g[a],s.h--}}this.G=null},Te.prototype.J=function(s,a,c,f){return this.i.add(String(s),a,!1,c,f)},Te.prototype.K=function(s,a,c,f){return this.i.add(String(s),a,!0,c,f)};function As(s,a,c,f){if(a=s.i.g[String(a)],!a)return!0;a=a.concat();let P=!0;for(let A=0;A<a.length;++A){const x=a[A];if(x&&!x.da&&x.capture==c){const B=x.listener,pe=x.ha||x.src;x.fa&&Un(s.i,x),P=B.call(pe,f)!==!1&&P}}return P&&!f.defaultPrevented}function fy(s,a){if(typeof s!="function")if(s&&typeof s.handleEvent=="function")s=d(s.handleEvent,s);else throw Error("Invalid listener argument");return Number(a)>2147483647?-1:l.setTimeout(s,a||0)}function qc(s){s.g=fy(()=>{s.g=null,s.i&&(s.i=!1,qc(s))},s.l);const a=s.h;s.h=null,s.m.apply(null,a)}class dy extends v{constructor(a,c){super(),this.m=a,this.l=c,this.h=null,this.i=!1,this.g=null}j(a){this.h=arguments,this.g?this.i=!0:qc(this)}N(){super.N(),this.g&&(l.clearTimeout(this.g),this.g=null,this.i=!1,this.h=null)}}function ii(s){v.call(this),this.h=s,this.g={}}S(ii,v);var Xc=[];function Jc(s){$(s.g,function(a,c){this.g.hasOwnProperty(c)&&Il(a)},s),s.g={}}ii.prototype.N=function(){ii.Z.N.call(this),Jc(this)},ii.prototype.handleEvent=function(){throw Error("EventHandler.handleEvent not implemented")};var Cl=l.JSON.stringify,py=l.JSON.parse,gy=class{stringify(s){return l.JSON.stringify(s,void 0)}parse(s){return l.JSON.parse(s,void 0)}};function Qc(){}function my(){}var si={OPEN:"a",hb:"b",ERROR:"c",tb:"d"};function Pl(){w.call(this,"d")}S(Pl,w);function Al(){w.call(this,"c")}S(Al,w);var hr={},Yc=null;function Rl(){return Yc=Yc||new Te}hr.Ia="serverreachability";function Zc(s){w.call(this,hr.Ia,s)}S(Zc,w);function oi(s){const a=Rl();Ne(a,new Zc(a))}hr.STAT_EVENT="statevent";function eh(s,a){w.call(this,hr.STAT_EVENT,s),this.stat=a}S(eh,w);function Oe(s){const a=Rl();Ne(a,new eh(a,s))}hr.Ja="timingevent";function th(s,a){w.call(this,hr.Ja,s),this.size=a}S(th,w);function li(s,a){if(typeof s!="function")throw Error("Fn must not be null and must be a function");return l.setTimeout(function(){s()},a)}function ai(){this.g=!0}ai.prototype.ua=function(){this.g=!1};function yy(s,a,c,f,P,A){s.info(function(){if(s.g)if(A){var x="",B=A.split("&");for(let Y=0;Y<B.length;Y++){var pe=B[Y].split("=");if(pe.length>1){const ye=pe[0];pe=pe[1];const yt=ye.split("_");x=yt.length>=2&&yt[1]=="type"?x+(ye+"="+pe+"&"):x+(ye+"=redacted&")}}}else x=null;else x=A;return"XMLHTTP REQ ("+f+") [attempt "+P+"]: "+a+`
`+c+`
`+x})}function vy(s,a,c,f,P,A,x){s.info(function(){return"XMLHTTP RESP ("+f+") [ attempt "+P+"]: "+a+`
`+c+`
`+A+" "+x})}function fr(s,a,c,f){s.info(function(){return"XMLHTTP TEXT ("+a+"): "+wy(s,c)+(f?" "+f:"")})}function _y(s,a){s.info(function(){return"TIMEOUT: "+a})}ai.prototype.info=function(){};function wy(s,a){if(!s.g)return a;if(!a)return null;try{const A=JSON.parse(a);if(A){for(s=0;s<A.length;s++)if(Array.isArray(A[s])){var c=A[s];if(!(c.length<2)){var f=c[1];if(Array.isArray(f)&&!(f.length<1)){var P=f[0];if(P!="noop"&&P!="stop"&&P!="close")for(let x=1;x<f.length;x++)f[x]=""}}}}return Cl(A)}catch{return a}}var Nl={NO_ERROR:0,TIMEOUT:8},Ey={},nh;function Ol(){}S(Ol,Qc),Ol.prototype.g=function(){return new XMLHttpRequest},nh=new Ol;function ui(s){return encodeURIComponent(String(s))}function Sy(s){var a=1;s=s.split(":");const c=[];for(;a>0&&s.length;)c.push(s.shift()),a--;return s.length&&c.push(s.join(":")),c}function Yt(s,a,c,f){this.j=s,this.i=a,this.l=c,this.S=f||1,this.V=new ii(this),this.H=45e3,this.J=null,this.o=!1,this.u=this.B=this.A=this.M=this.F=this.T=this.D=null,this.G=[],this.g=null,this.C=0,this.m=this.v=null,this.X=-1,this.K=!1,this.P=0,this.O=null,this.W=this.L=this.U=this.R=!1,this.h=new rh}function rh(){this.i=null,this.g="",this.h=!1}var ih={},Dl={};function Ll(s,a,c){s.M=1,s.A=Ns(mt(a)),s.u=c,s.R=!0,sh(s,null)}function sh(s,a){s.F=Date.now(),Rs(s),s.B=mt(s.A);var c=s.B,f=s.S;Array.isArray(f)||(f=[String(f)]),vh(c.i,"t",f),s.C=0,c=s.j.L,s.h=new rh,s.g=Uh(s.j,c?a:null,!s.u),s.P>0&&(s.O=new dy(d(s.Y,s,s.g),s.P)),a=s.V,c=s.g,f=s.ba;var P="readystatechange";Array.isArray(P)||(P&&(Xc[0]=P.toString()),P=Xc);for(let A=0;A<P.length;A++){const x=Hc(c,P[A],f||a.handleEvent,!1,a.h||a);if(!x)break;a.g[x.key]=x}a=s.J?re(s.J):{},s.u?(s.v||(s.v="POST"),a["Content-Type"]="application/x-www-form-urlencoded",s.g.ea(s.B,s.v,s.u,a)):(s.v="GET",s.g.ea(s.B,s.v,null,a)),oi(),yy(s.i,s.v,s.B,s.l,s.S,s.u)}Yt.prototype.ba=function(s){s=s.target;const a=this.O;a&&tn(s)==3?a.j():this.Y(s)},Yt.prototype.Y=function(s){try{if(s==this.g)e:{const B=tn(this.g),pe=this.g.ya(),Y=this.g.ca();if(!(B<3)&&(B!=3||this.g&&(this.h.h||this.g.la()||kh(this.g)))){this.K||B!=4||pe==7||(pe==8||Y<=0?oi(3):oi(2)),xl(this);var a=this.g.ca();this.X=a;var c=Iy(this);if(this.o=a==200,vy(this.i,this.v,this.B,this.l,this.S,B,a),this.o){if(this.U&&!this.L){t:{if(this.g){var f,P=this.g;if((f=P.g?P.g.getResponseHeader("X-HTTP-Initial-Response"):null)&&!y(f)){var A=f;break t}}A=null}if(s=A)fr(this.i,this.l,s,"Initial handshake response via X-HTTP-Initial-Response"),this.L=!0,Ml(this,s);else{this.o=!1,this.m=3,Oe(12),Fn(this),ci(this);break e}}if(this.R){s=!0;let ye;for(;!this.K&&this.C<c.length;)if(ye=Ty(this,c),ye==Dl){B==4&&(this.m=4,Oe(14),s=!1),fr(this.i,this.l,null,"[Incomplete Response]");break}else if(ye==ih){this.m=4,Oe(15),fr(this.i,this.l,c,"[Invalid Chunk]"),s=!1;break}else fr(this.i,this.l,ye,null),Ml(this,ye);if(oh(this)&&this.C!=0&&(this.h.g=this.h.g.slice(this.C),this.C=0),B!=4||c.length!=0||this.h.h||(this.m=1,Oe(16),s=!1),this.o=this.o&&s,!s)fr(this.i,this.l,c,"[Invalid Chunked Response]"),Fn(this),ci(this);else if(c.length>0&&!this.W){this.W=!0;var x=this.j;x.g==this&&x.aa&&!x.P&&(x.j.info("Great, no buffering proxy detected. Bytes received: "+c.length),Bl(x),x.P=!0,Oe(11))}}else fr(this.i,this.l,c,null),Ml(this,c);B==4&&Fn(this),this.o&&!this.K&&(B==4?Dh(this.j,this):(this.o=!1,Rs(this)))}else jy(this.g),a==400&&c.indexOf("Unknown SID")>0?(this.m=3,Oe(12)):(this.m=0,Oe(13)),Fn(this),ci(this)}}}catch{}finally{}};function Iy(s){if(!oh(s))return s.g.la();const a=kh(s.g);if(a==="")return"";let c="";const f=a.length,P=tn(s.g)==4;if(!s.h.i){if(typeof TextDecoder>"u")return Fn(s),ci(s),"";s.h.i=new l.TextDecoder}for(let A=0;A<f;A++)s.h.h=!0,c+=s.h.i.decode(a[A],{stream:!(P&&A==f-1)});return a.length=0,s.h.g+=c,s.C=0,s.h.g}function oh(s){return s.g?s.v=="GET"&&s.M!=2&&s.j.Aa:!1}function Ty(s,a){var c=s.C,f=a.indexOf(`
`,c);return f==-1?Dl:(c=Number(a.substring(c,f)),isNaN(c)?ih:(f+=1,f+c>a.length?Dl:(a=a.slice(f,f+c),s.C=f+c,a)))}Yt.prototype.cancel=function(){this.K=!0,Fn(this)};function Rs(s){s.T=Date.now()+s.H,lh(s,s.H)}function lh(s,a){if(s.D!=null)throw Error("WatchDog timer not null");s.D=li(d(s.aa,s),a)}function xl(s){s.D&&(l.clearTimeout(s.D),s.D=null)}Yt.prototype.aa=function(){this.D=null;const s=Date.now();s-this.T>=0?(_y(this.i,this.B),this.M!=2&&(oi(),Oe(17)),Fn(this),this.m=2,ci(this)):lh(this,this.T-s)};function ci(s){s.j.I==0||s.K||Dh(s.j,s)}function Fn(s){xl(s);var a=s.O;a&&typeof a.dispose=="function"&&a.dispose(),s.O=null,Jc(s.V),s.g&&(a=s.g,s.g=null,a.abort(),a.dispose())}function Ml(s,a){try{var c=s.j;if(c.I!=0&&(c.g==s||Ul(c.h,s))){if(!s.L&&Ul(c.h,s)&&c.I==3){try{var f=c.Ba.g.parse(a)}catch{f=null}if(Array.isArray(f)&&f.length==3){var P=f;if(P[0]==0){e:if(!c.v){if(c.g)if(c.g.F+3e3<s.F)Ms(c),Ls(c);else break e;bl(c),Oe(18)}}else c.xa=P[1],0<c.xa-c.K&&P[2]<37500&&c.F&&c.A==0&&!c.C&&(c.C=li(d(c.Va,c),6e3));ch(c.h)<=1&&c.ta&&(c.ta=void 0)}else Vn(c,11)}else if((s.L||c.g==s)&&Ms(c),!y(a))for(P=c.Ba.g.parse(a),a=0;a<P.length;a++){let Y=P[a];const ye=Y[0];if(!(ye<=c.K))if(c.K=ye,Y=Y[1],c.I==2)if(Y[0]=="c"){c.M=Y[1],c.ba=Y[2];const yt=Y[3];yt!=null&&(c.ka=yt,c.j.info("VER="+c.ka));const zn=Y[4];zn!=null&&(c.za=zn,c.j.info("SVER="+c.za));const nn=Y[5];nn!=null&&typeof nn=="number"&&nn>0&&(f=1.5*nn,c.O=f,c.j.info("backChannelRequestTimeoutMs_="+f)),f=c;const rn=s.g;if(rn){const Us=rn.g?rn.g.getResponseHeader("X-Client-Wire-Protocol"):null;if(Us){var A=f.h;A.g||Us.indexOf("spdy")==-1&&Us.indexOf("quic")==-1&&Us.indexOf("h2")==-1||(A.j=A.l,A.g=new Set,A.h&&(Fl(A,A.h),A.h=null))}if(f.G){const Hl=rn.g?rn.g.getResponseHeader("X-HTTP-Session-Id"):null;Hl&&(f.wa=Hl,ee(f.J,f.G,Hl))}}c.I=3,c.l&&c.l.ra(),c.aa&&(c.T=Date.now()-s.F,c.j.info("Handshake RTT: "+c.T+"ms")),f=c;var x=s;if(f.na=Mh(f,f.L?f.ba:null,f.W),x.L){hh(f.h,x);var B=x,pe=f.O;pe&&(B.H=pe),B.D&&(xl(B),Rs(B)),f.g=x}else Nh(f);c.i.length>0&&xs(c)}else Y[0]!="stop"&&Y[0]!="close"||Vn(c,7);else c.I==3&&(Y[0]=="stop"||Y[0]=="close"?Y[0]=="stop"?Vn(c,7):$l(c):Y[0]!="noop"&&c.l&&c.l.qa(Y),c.A=0)}}oi(4)}catch{}}var ky=class{constructor(s,a){this.g=s,this.map=a}};function ah(s){this.l=s||10,l.PerformanceNavigationTiming?(s=l.performance.getEntriesByType("navigation"),s=s.length>0&&(s[0].nextHopProtocol=="hq"||s[0].nextHopProtocol=="h2")):s=!!(l.chrome&&l.chrome.loadTimes&&l.chrome.loadTimes()&&l.chrome.loadTimes().wasFetchedViaSpdy),this.j=s?this.l:1,this.g=null,this.j>1&&(this.g=new Set),this.h=null,this.i=[]}function uh(s){return s.h?!0:s.g?s.g.size>=s.j:!1}function ch(s){return s.h?1:s.g?s.g.size:0}function Ul(s,a){return s.h?s.h==a:s.g?s.g.has(a):!1}function Fl(s,a){s.g?s.g.add(a):s.h=a}function hh(s,a){s.h&&s.h==a?s.h=null:s.g&&s.g.has(a)&&s.g.delete(a)}ah.prototype.cancel=function(){if(this.i=fh(this),this.h)this.h.cancel(),this.h=null;else if(this.g&&this.g.size!==0){for(const s of this.g.values())s.cancel();this.g.clear()}};function fh(s){if(s.h!=null)return s.i.concat(s.h.G);if(s.g!=null&&s.g.size!==0){let a=s.i;for(const c of s.g.values())a=a.concat(c.G);return a}return N(s.i)}var dh=RegExp("^(?:([^:/?#.]+):)?(?://(?:([^\\\\/?#]*)@)?([^\\\\/?#]*?)(?::([0-9]+))?(?=[\\\\/?#]|$))?([^?#]+)?(?:\\?([^#]*))?(?:#([\\s\\S]*))?$");function Cy(s,a){if(s){s=s.split("&");for(let c=0;c<s.length;c++){const f=s[c].indexOf("=");let P,A=null;f>=0?(P=s[c].substring(0,f),A=s[c].substring(f+1)):P=s[c],a(P,A?decodeURIComponent(A.replace(/\+/g," ")):"")}}}function Zt(s){this.g=this.o=this.j="",this.u=null,this.m=this.h="",this.l=!1;let a;s instanceof Zt?(this.l=s.l,hi(this,s.j),this.o=s.o,this.g=s.g,fi(this,s.u),this.h=s.h,jl(this,_h(s.i)),this.m=s.m):s&&(a=String(s).match(dh))?(this.l=!1,hi(this,a[1]||"",!0),this.o=di(a[2]||""),this.g=di(a[3]||"",!0),fi(this,a[4]),this.h=di(a[5]||"",!0),jl(this,a[6]||"",!0),this.m=di(a[7]||"")):(this.l=!1,this.i=new gi(null,this.l))}Zt.prototype.toString=function(){const s=[];var a=this.j;a&&s.push(pi(a,ph,!0),":");var c=this.g;return(c||a=="file")&&(s.push("//"),(a=this.o)&&s.push(pi(a,ph,!0),"@"),s.push(ui(c).replace(/%25([0-9a-fA-F]{2})/g,"%$1")),c=this.u,c!=null&&s.push(":",String(c))),(c=this.h)&&(this.g&&c.charAt(0)!="/"&&s.push("/"),s.push(pi(c,c.charAt(0)=="/"?Ry:Ay,!0))),(c=this.i.toString())&&s.push("?",c),(c=this.m)&&s.push("#",pi(c,Oy)),s.join("")},Zt.prototype.resolve=function(s){const a=mt(this);let c=!!s.j;c?hi(a,s.j):c=!!s.o,c?a.o=s.o:c=!!s.g,c?a.g=s.g:c=s.u!=null;var f=s.h;if(c)fi(a,s.u);else if(c=!!s.h){if(f.charAt(0)!="/")if(this.g&&!this.h)f="/"+f;else{var P=a.h.lastIndexOf("/");P!=-1&&(f=a.h.slice(0,P+1)+f)}if(P=f,P==".."||P==".")f="";else if(P.indexOf("./")!=-1||P.indexOf("/.")!=-1){f=P.lastIndexOf("/",0)==0,P=P.split("/");const A=[];for(let x=0;x<P.length;){const B=P[x++];B=="."?f&&x==P.length&&A.push(""):B==".."?((A.length>1||A.length==1&&A[0]!="")&&A.pop(),f&&x==P.length&&A.push("")):(A.push(B),f=!0)}f=A.join("/")}else f=P}return c?a.h=f:c=s.i.toString()!=="",c?jl(a,_h(s.i)):c=!!s.m,c&&(a.m=s.m),a};function mt(s){return new Zt(s)}function hi(s,a,c){s.j=c?di(a,!0):a,s.j&&(s.j=s.j.replace(/:$/,""))}function fi(s,a){if(a){if(a=Number(a),isNaN(a)||a<0)throw Error("Bad port number "+a);s.u=a}else s.u=null}function jl(s,a,c){a instanceof gi?(s.i=a,Dy(s.i,s.l)):(c||(a=pi(a,Ny)),s.i=new gi(a,s.l))}function ee(s,a,c){s.i.set(a,c)}function Ns(s){return ee(s,"zx",Math.floor(Math.random()*2147483648).toString(36)+Math.abs(Math.floor(Math.random()*2147483648)^Date.now()).toString(36)),s}function di(s,a){return s?a?decodeURI(s.replace(/%25/g,"%2525")):decodeURIComponent(s):""}function pi(s,a,c){return typeof s=="string"?(s=encodeURI(s).replace(a,Py),c&&(s=s.replace(/%25([0-9a-fA-F]{2})/g,"%$1")),s):null}function Py(s){return s=s.charCodeAt(0),"%"+(s>>4&15).toString(16)+(s&15).toString(16)}var ph=/[#\/\?@]/g,Ay=/[#\?:]/g,Ry=/[#\?]/g,Ny=/[#\?@]/g,Oy=/#/g;function gi(s,a){this.h=this.g=null,this.i=s||null,this.j=!!a}function jn(s){s.g||(s.g=new Map,s.h=0,s.i&&Cy(s.i,function(a,c){s.add(decodeURIComponent(a.replace(/\+/g," ")),c)}))}t=gi.prototype,t.add=function(s,a){jn(this),this.i=null,s=dr(this,s);let c=this.g.get(s);return c||this.g.set(s,c=[]),c.push(a),this.h+=1,this};function gh(s,a){jn(s),a=dr(s,a),s.g.has(a)&&(s.i=null,s.h-=s.g.get(a).length,s.g.delete(a))}function mh(s,a){return jn(s),a=dr(s,a),s.g.has(a)}t.forEach=function(s,a){jn(this),this.g.forEach(function(c,f){c.forEach(function(P){s.call(a,P,f,this)},this)},this)};function yh(s,a){jn(s);let c=[];if(typeof a=="string")mh(s,a)&&(c=c.concat(s.g.get(dr(s,a))));else for(s=Array.from(s.g.values()),a=0;a<s.length;a++)c=c.concat(s[a]);return c}t.set=function(s,a){return jn(this),this.i=null,s=dr(this,s),mh(this,s)&&(this.h-=this.g.get(s).length),this.g.set(s,[a]),this.h+=1,this},t.get=function(s,a){return s?(s=yh(this,s),s.length>0?String(s[0]):a):a};function vh(s,a,c){gh(s,a),c.length>0&&(s.i=null,s.g.set(dr(s,a),N(c)),s.h+=c.length)}t.toString=function(){if(this.i)return this.i;if(!this.g)return"";const s=[],a=Array.from(this.g.keys());for(let f=0;f<a.length;f++){var c=a[f];const P=ui(c);c=yh(this,c);for(let A=0;A<c.length;A++){let x=P;c[A]!==""&&(x+="="+ui(c[A])),s.push(x)}}return this.i=s.join("&")};function _h(s){const a=new gi;return a.i=s.i,s.g&&(a.g=new Map(s.g),a.h=s.h),a}function dr(s,a){return a=String(a),s.j&&(a=a.toLowerCase()),a}function Dy(s,a){a&&!s.j&&(jn(s),s.i=null,s.g.forEach(function(c,f){const P=f.toLowerCase();f!=P&&(gh(this,f),vh(this,P,c))},s)),s.j=a}function Ly(s,a){const c=new ai;if(l.Image){const f=new Image;f.onload=k(en,c,"TestLoadImage: loaded",!0,a,f),f.onerror=k(en,c,"TestLoadImage: error",!1,a,f),f.onabort=k(en,c,"TestLoadImage: abort",!1,a,f),f.ontimeout=k(en,c,"TestLoadImage: timeout",!1,a,f),l.setTimeout(function(){f.ontimeout&&f.ontimeout()},1e4),f.src=s}else a(!1)}function xy(s,a){const c=new ai,f=new AbortController,P=setTimeout(()=>{f.abort(),en(c,"TestPingServer: timeout",!1,a)},1e4);fetch(s,{signal:f.signal}).then(A=>{clearTimeout(P),A.ok?en(c,"TestPingServer: ok",!0,a):en(c,"TestPingServer: server error",!1,a)}).catch(()=>{clearTimeout(P),en(c,"TestPingServer: error",!1,a)})}function en(s,a,c,f,P){try{P&&(P.onload=null,P.onerror=null,P.onabort=null,P.ontimeout=null),f(c)}catch{}}function My(){this.g=new gy}function Vl(s){this.i=s.Sb||null,this.h=s.ab||!1}S(Vl,Qc),Vl.prototype.g=function(){return new Os(this.i,this.h)};function Os(s,a){Te.call(this),this.H=s,this.o=a,this.m=void 0,this.status=this.readyState=0,this.responseType=this.responseText=this.response=this.statusText="",this.onreadystatechange=null,this.A=new Headers,this.h=null,this.F="GET",this.D="",this.g=!1,this.B=this.j=this.l=null,this.v=new AbortController}S(Os,Te),t=Os.prototype,t.open=function(s,a){if(this.readyState!=0)throw this.abort(),Error("Error reopening a connection");this.F=s,this.D=a,this.readyState=1,yi(this)},t.send=function(s){if(this.readyState!=1)throw this.abort(),Error("need to call open() first. ");if(this.v.signal.aborted)throw this.abort(),Error("Request was aborted.");this.g=!0;const a={headers:this.A,method:this.F,credentials:this.m,cache:void 0,signal:this.v.signal};s&&(a.body=s),(this.H||l).fetch(new Request(this.D,a)).then(this.Pa.bind(this),this.ga.bind(this))},t.abort=function(){this.response=this.responseText="",this.A=new Headers,this.status=0,this.v.abort(),this.j&&this.j.cancel("Request was aborted.").catch(()=>{}),this.readyState>=1&&this.g&&this.readyState!=4&&(this.g=!1,mi(this)),this.readyState=0},t.Pa=function(s){if(this.g&&(this.l=s,this.h||(this.status=this.l.status,this.statusText=this.l.statusText,this.h=s.headers,this.readyState=2,yi(this)),this.g&&(this.readyState=3,yi(this),this.g)))if(this.responseType==="arraybuffer")s.arrayBuffer().then(this.Na.bind(this),this.ga.bind(this));else if(typeof l.ReadableStream<"u"&&"body"in s){if(this.j=s.body.getReader(),this.o){if(this.responseType)throw Error('responseType must be empty for "streamBinaryChunks" mode responses.');this.response=[]}else this.response=this.responseText="",this.B=new TextDecoder;wh(this)}else s.text().then(this.Oa.bind(this),this.ga.bind(this))};function wh(s){s.j.read().then(s.Ma.bind(s)).catch(s.ga.bind(s))}t.Ma=function(s){if(this.g){if(this.o&&s.value)this.response.push(s.value);else if(!this.o){var a=s.value?s.value:new Uint8Array(0);(a=this.B.decode(a,{stream:!s.done}))&&(this.response=this.responseText+=a)}s.done?mi(this):yi(this),this.readyState==3&&wh(this)}},t.Oa=function(s){this.g&&(this.response=this.responseText=s,mi(this))},t.Na=function(s){this.g&&(this.response=s,mi(this))},t.ga=function(){this.g&&mi(this)};function mi(s){s.readyState=4,s.l=null,s.j=null,s.B=null,yi(s)}t.setRequestHeader=function(s,a){this.A.append(s,a)},t.getResponseHeader=function(s){return this.h&&this.h.get(s.toLowerCase())||""},t.getAllResponseHeaders=function(){if(!this.h)return"";const s=[],a=this.h.entries();for(var c=a.next();!c.done;)c=c.value,s.push(c[0]+": "+c[1]),c=a.next();return s.join(`\r
`)};function yi(s){s.onreadystatechange&&s.onreadystatechange.call(s)}Object.defineProperty(Os.prototype,"withCredentials",{get:function(){return this.m==="include"},set:function(s){this.m=s?"include":"same-origin"}});function Eh(s){let a="";return $(s,function(c,f){a+=f,a+=":",a+=c,a+=`\r
`}),a}function zl(s,a,c){e:{for(f in c){var f=!1;break e}f=!0}f||(c=Eh(c),typeof s=="string"?c!=null&&ui(c):ee(s,a,c))}function ce(s){Te.call(this),this.headers=new Map,this.L=s||null,this.h=!1,this.g=null,this.D="",this.o=0,this.l="",this.j=this.B=this.v=this.A=!1,this.m=null,this.F="",this.H=!1}S(ce,Te);var Uy=/^https?$/i,Fy=["POST","PUT"];t=ce.prototype,t.Fa=function(s){this.H=s},t.ea=function(s,a,c,f){if(this.g)throw Error("[goog.net.XhrIo] Object is active with another request="+this.D+"; newUri="+s);a=a?a.toUpperCase():"GET",this.D=s,this.l="",this.o=0,this.A=!1,this.h=!0,this.g=this.L?this.L.g():nh.g(),this.g.onreadystatechange=E(d(this.Ca,this));try{this.B=!0,this.g.open(a,String(s),!0),this.B=!1}catch(A){Sh(this,A);return}if(s=c||"",c=new Map(this.headers),f)if(Object.getPrototypeOf(f)===Object.prototype)for(var P in f)c.set(P,f[P]);else if(typeof f.keys=="function"&&typeof f.get=="function")for(const A of f.keys())c.set(A,f.get(A));else throw Error("Unknown input type for opt_headers: "+String(f));f=Array.from(c.keys()).find(A=>A.toLowerCase()=="content-type"),P=l.FormData&&s instanceof l.FormData,!(Array.prototype.indexOf.call(Fy,a,void 0)>=0)||f||P||c.set("Content-Type","application/x-www-form-urlencoded;charset=utf-8");for(const[A,x]of c)this.g.setRequestHeader(A,x);this.F&&(this.g.responseType=this.F),"withCredentials"in this.g&&this.g.withCredentials!==this.H&&(this.g.withCredentials=this.H);try{this.m&&(clearTimeout(this.m),this.m=null),this.v=!0,this.g.send(s),this.v=!1}catch(A){Sh(this,A)}};function Sh(s,a){s.h=!1,s.g&&(s.j=!0,s.g.abort(),s.j=!1),s.l=a,s.o=5,Ih(s),Ds(s)}function Ih(s){s.A||(s.A=!0,Ne(s,"complete"),Ne(s,"error"))}t.abort=function(s){this.g&&this.h&&(this.h=!1,this.j=!0,this.g.abort(),this.j=!1,this.o=s||7,Ne(this,"complete"),Ne(this,"abort"),Ds(this))},t.N=function(){this.g&&(this.h&&(this.h=!1,this.j=!0,this.g.abort(),this.j=!1),Ds(this,!0)),ce.Z.N.call(this)},t.Ca=function(){this.u||(this.B||this.v||this.j?Th(this):this.Xa())},t.Xa=function(){Th(this)};function Th(s){if(s.h&&typeof o<"u"){if(s.v&&tn(s)==4)setTimeout(s.Ca.bind(s),0);else if(Ne(s,"readystatechange"),tn(s)==4){s.h=!1;try{const A=s.ca();e:switch(A){case 200:case 201:case 202:case 204:case 206:case 304:case 1223:var a=!0;break e;default:a=!1}var c;if(!(c=a)){var f;if(f=A===0){let x=String(s.D).match(dh)[1]||null;!x&&l.self&&l.self.location&&(x=l.self.location.protocol.slice(0,-1)),f=!Uy.test(x?x.toLowerCase():"")}c=f}if(c)Ne(s,"complete"),Ne(s,"success");else{s.o=6;try{var P=tn(s)>2?s.g.statusText:""}catch{P=""}s.l=P+" ["+s.ca()+"]",Ih(s)}}finally{Ds(s)}}}}function Ds(s,a){if(s.g){s.m&&(clearTimeout(s.m),s.m=null);const c=s.g;s.g=null,a||Ne(s,"ready");try{c.onreadystatechange=null}catch{}}}t.isActive=function(){return!!this.g};function tn(s){return s.g?s.g.readyState:0}t.ca=function(){try{return tn(this)>2?this.g.status:-1}catch{return-1}},t.la=function(){try{return this.g?this.g.responseText:""}catch{return""}},t.La=function(s){if(this.g){var a=this.g.responseText;return s&&a.indexOf(s)==0&&(a=a.substring(s.length)),py(a)}};function kh(s){try{if(!s.g)return null;if("response"in s.g)return s.g.response;switch(s.F){case"":case"text":return s.g.responseText;case"arraybuffer":if("mozResponseArrayBuffer"in s.g)return s.g.mozResponseArrayBuffer}return null}catch{return null}}function jy(s){const a={};s=(s.g&&tn(s)>=2&&s.g.getAllResponseHeaders()||"").split(`\r
`);for(let f=0;f<s.length;f++){if(y(s[f]))continue;var c=Sy(s[f]);const P=c[0];if(c=c[1],typeof c!="string")continue;c=c.trim();const A=a[P]||[];a[P]=A,A.push(c)}b(a,function(f){return f.join(", ")})}t.ya=function(){return this.o},t.Ha=function(){return typeof this.l=="string"?this.l:String(this.l)};function vi(s,a,c){return c&&c.internalChannelParams&&c.internalChannelParams[s]||a}function Ch(s){this.za=0,this.i=[],this.j=new ai,this.ba=this.na=this.J=this.W=this.g=this.wa=this.G=this.H=this.u=this.U=this.o=null,this.Ya=this.V=0,this.Sa=vi("failFast",!1,s),this.F=this.C=this.v=this.m=this.l=null,this.X=!0,this.xa=this.K=-1,this.Y=this.A=this.D=0,this.Qa=vi("baseRetryDelayMs",5e3,s),this.Za=vi("retryDelaySeedMs",1e4,s),this.Ta=vi("forwardChannelMaxRetries",2,s),this.va=vi("forwardChannelRequestTimeoutMs",2e4,s),this.ma=s&&s.xmlHttpFactory||void 0,this.Ua=s&&s.Rb||void 0,this.Aa=s&&s.useFetchStreams||!1,this.O=void 0,this.L=s&&s.supportsCrossDomainXhr||!1,this.M="",this.h=new ah(s&&s.concurrentRequestLimit),this.Ba=new My,this.S=s&&s.fastHandshake||!1,this.R=s&&s.encodeInitMessageHeaders||!1,this.S&&this.R&&(this.R=!1),this.Ra=s&&s.Pb||!1,s&&s.ua&&this.j.ua(),s&&s.forceLongPolling&&(this.X=!1),this.aa=!this.S&&this.X&&s&&s.detectBufferingProxy||!1,this.ia=void 0,s&&s.longPollingTimeout&&s.longPollingTimeout>0&&(this.ia=s.longPollingTimeout),this.ta=void 0,this.T=0,this.P=!1,this.ja=this.B=null}t=Ch.prototype,t.ka=8,t.I=1,t.connect=function(s,a,c,f){Oe(0),this.W=s,this.H=a||{},c&&f!==void 0&&(this.H.OSID=c,this.H.OAID=f),this.F=this.X,this.J=Mh(this,null,this.W),xs(this)};function $l(s){if(Ph(s),s.I==3){var a=s.V++,c=mt(s.J);if(ee(c,"SID",s.M),ee(c,"RID",a),ee(c,"TYPE","terminate"),_i(s,c),a=new Yt(s,s.j,a),a.M=2,a.A=Ns(mt(c)),c=!1,l.navigator&&l.navigator.sendBeacon)try{c=l.navigator.sendBeacon(a.A.toString(),"")}catch{}!c&&l.Image&&(new Image().src=a.A,c=!0),c||(a.g=Uh(a.j,null),a.g.ea(a.A)),a.F=Date.now(),Rs(a)}xh(s)}function Ls(s){s.g&&(Bl(s),s.g.cancel(),s.g=null)}function Ph(s){Ls(s),s.v&&(l.clearTimeout(s.v),s.v=null),Ms(s),s.h.cancel(),s.m&&(typeof s.m=="number"&&l.clearTimeout(s.m),s.m=null)}function xs(s){if(!uh(s.h)&&!s.m){s.m=!0;var a=s.Ea;M||p(),U||(M(),U=!0),g.add(a,s),s.D=0}}function Vy(s,a){return ch(s.h)>=s.h.j-(s.m?1:0)?!1:s.m?(s.i=a.G.concat(s.i),!0):s.I==1||s.I==2||s.D>=(s.Sa?0:s.Ta)?!1:(s.m=li(d(s.Ea,s,a),Lh(s,s.D)),s.D++,!0)}t.Ea=function(s){if(this.m)if(this.m=null,this.I==1){if(!s){this.V=Math.floor(Math.random()*1e5),s=this.V++;const P=new Yt(this,this.j,s);let A=this.o;if(this.U&&(A?(A=re(A),Mn(A,this.U)):A=this.U),this.u!==null||this.R||(P.J=A,A=null),this.S)e:{for(var a=0,c=0;c<this.i.length;c++){t:{var f=this.i[c];if("__data__"in f.map&&(f=f.map.__data__,typeof f=="string")){f=f.length;break t}f=void 0}if(f===void 0)break;if(a+=f,a>4096){a=c;break e}if(a===4096||c===this.i.length-1){a=c+1;break e}}a=1e3}else a=1e3;a=Rh(this,P,a),c=mt(this.J),ee(c,"RID",s),ee(c,"CVER",22),this.G&&ee(c,"X-HTTP-Session-Id",this.G),_i(this,c),A&&(this.R?a="headers="+ui(Eh(A))+"&"+a:this.u&&zl(c,this.u,A)),Fl(this.h,P),this.Ra&&ee(c,"TYPE","init"),this.S?(ee(c,"$req",a),ee(c,"SID","null"),P.U=!0,Ll(P,c,null)):Ll(P,c,a),this.I=2}}else this.I==3&&(s?Ah(this,s):this.i.length==0||uh(this.h)||Ah(this))};function Ah(s,a){var c;a?c=a.l:c=s.V++;const f=mt(s.J);ee(f,"SID",s.M),ee(f,"RID",c),ee(f,"AID",s.K),_i(s,f),s.u&&s.o&&zl(f,s.u,s.o),c=new Yt(s,s.j,c,s.D+1),s.u===null&&(c.J=s.o),a&&(s.i=a.G.concat(s.i)),a=Rh(s,c,1e3),c.H=Math.round(s.va*.5)+Math.round(s.va*.5*Math.random()),Fl(s.h,c),Ll(c,f,a)}function _i(s,a){s.H&&$(s.H,function(c,f){ee(a,f,c)}),s.l&&$({},function(c,f){ee(a,f,c)})}function Rh(s,a,c){c=Math.min(s.i.length,c);const f=s.l?d(s.l.Ka,s.l,s):null;e:{var P=s.i;let B=-1;for(;;){const pe=["count="+c];B==-1?c>0?(B=P[0].g,pe.push("ofs="+B)):B=0:pe.push("ofs="+B);let Y=!0;for(let ye=0;ye<c;ye++){var A=P[ye].g;const yt=P[ye].map;if(A-=B,A<0)B=Math.max(0,P[ye].g-100),Y=!1;else try{A="req"+A+"_"||"";try{var x=yt instanceof Map?yt:Object.entries(yt);for(const[zn,nn]of x){let rn=nn;u(nn)&&(rn=Cl(nn)),pe.push(A+zn+"="+encodeURIComponent(rn))}}catch(zn){throw pe.push(A+"type="+encodeURIComponent("_badmap")),zn}}catch{f&&f(yt)}}if(Y){x=pe.join("&");break e}}x=void 0}return s=s.i.splice(0,c),a.G=s,x}function Nh(s){if(!s.g&&!s.v){s.Y=1;var a=s.Da;M||p(),U||(M(),U=!0),g.add(a,s),s.A=0}}function bl(s){return s.g||s.v||s.A>=3?!1:(s.Y++,s.v=li(d(s.Da,s),Lh(s,s.A)),s.A++,!0)}t.Da=function(){if(this.v=null,Oh(this),this.aa&&!(this.P||this.g==null||this.T<=0)){var s=4*this.T;this.j.info("BP detection timer enabled: "+s),this.B=li(d(this.Wa,this),s)}},t.Wa=function(){this.B&&(this.B=null,this.j.info("BP detection timeout reached."),this.j.info("Buffering proxy detected and switch to long-polling!"),this.F=!1,this.P=!0,Oe(10),Ls(this),Oh(this))};function Bl(s){s.B!=null&&(l.clearTimeout(s.B),s.B=null)}function Oh(s){s.g=new Yt(s,s.j,"rpc",s.Y),s.u===null&&(s.g.J=s.o),s.g.P=0;var a=mt(s.na);ee(a,"RID","rpc"),ee(a,"SID",s.M),ee(a,"AID",s.K),ee(a,"CI",s.F?"0":"1"),!s.F&&s.ia&&ee(a,"TO",s.ia),ee(a,"TYPE","xmlhttp"),_i(s,a),s.u&&s.o&&zl(a,s.u,s.o),s.O&&(s.g.H=s.O);var c=s.g;s=s.ba,c.M=1,c.A=Ns(mt(a)),c.u=null,c.R=!0,sh(c,s)}t.Va=function(){this.C!=null&&(this.C=null,Ls(this),bl(this),Oe(19))};function Ms(s){s.C!=null&&(l.clearTimeout(s.C),s.C=null)}function Dh(s,a){var c=null;if(s.g==a){Ms(s),Bl(s),s.g=null;var f=2}else if(Ul(s.h,a))c=a.G,hh(s.h,a),f=1;else return;if(s.I!=0){if(a.o)if(f==1){c=a.u?a.u.length:0,a=Date.now()-a.F;var P=s.D;f=Rl(),Ne(f,new th(f,c)),xs(s)}else Nh(s);else if(P=a.m,P==3||P==0&&a.X>0||!(f==1&&Vy(s,a)||f==2&&bl(s)))switch(c&&c.length>0&&(a=s.h,a.i=a.i.concat(c)),P){case 1:Vn(s,5);break;case 4:Vn(s,10);break;case 3:Vn(s,6);break;default:Vn(s,2)}}}function Lh(s,a){let c=s.Qa+Math.floor(Math.random()*s.Za);return s.isActive()||(c*=2),c*a}function Vn(s,a){if(s.j.info("Error code "+a),a==2){var c=d(s.bb,s),f=s.Ua;const P=!f;f=new Zt(f||"//www.google.com/images/cleardot.gif"),l.location&&l.location.protocol=="http"||hi(f,"https"),Ns(f),P?Ly(f.toString(),c):xy(f.toString(),c)}else Oe(2);s.I=0,s.l&&s.l.pa(a),xh(s),Ph(s)}t.bb=function(s){s?(this.j.info("Successfully pinged google.com"),Oe(2)):(this.j.info("Failed to ping google.com"),Oe(1))};function xh(s){if(s.I=0,s.ja=[],s.l){const a=fh(s.h);(a.length!=0||s.i.length!=0)&&(O(s.ja,a),O(s.ja,s.i),s.h.i.length=0,N(s.i),s.i.length=0),s.l.oa()}}function Mh(s,a,c){var f=c instanceof Zt?mt(c):new Zt(c);if(f.g!="")a&&(f.g=a+"."+f.g),fi(f,f.u);else{var P=l.location;f=P.protocol,a=a?a+"."+P.hostname:P.hostname,P=+P.port;const A=new Zt(null);f&&hi(A,f),a&&(A.g=a),P&&fi(A,P),c&&(A.h=c),f=A}return c=s.G,a=s.wa,c&&a&&ee(f,c,a),ee(f,"VER",s.ka),_i(s,f),f}function Uh(s,a,c){if(a&&!s.L)throw Error("Can't create secondary domain capable XhrIo object.");return a=s.Aa&&!s.ma?new ce(new Vl({ab:c})):new ce(s.ma),a.Fa(s.L),a}t.isActive=function(){return!!this.l&&this.l.isActive(this)};function Fh(){}t=Fh.prototype,t.ra=function(){},t.qa=function(){},t.pa=function(){},t.oa=function(){},t.isActive=function(){return!0},t.Ka=function(){};function Qe(s,a){Te.call(this),this.g=new Ch(a),this.l=s,this.h=a&&a.messageUrlParams||null,s=a&&a.messageHeaders||null,a&&a.clientProtocolHeaderRequired&&(s?s["X-Client-Protocol"]="webchannel":s={"X-Client-Protocol":"webchannel"}),this.g.o=s,s=a&&a.initMessageHeaders||null,a&&a.messageContentType&&(s?s["X-WebChannel-Content-Type"]=a.messageContentType:s={"X-WebChannel-Content-Type":a.messageContentType}),a&&a.sa&&(s?s["X-WebChannel-Client-Profile"]=a.sa:s={"X-WebChannel-Client-Profile":a.sa}),this.g.U=s,(s=a&&a.Qb)&&!y(s)&&(this.g.u=s),this.A=a&&a.supportsCrossDomainXhr||!1,this.v=a&&a.sendRawJson||!1,(a=a&&a.httpSessionIdParam)&&!y(a)&&(this.g.G=a,s=this.h,s!==null&&a in s&&(s=this.h,a in s&&delete s[a])),this.j=new pr(this)}S(Qe,Te),Qe.prototype.m=function(){this.g.l=this.j,this.A&&(this.g.L=!0),this.g.connect(this.l,this.h||void 0)},Qe.prototype.close=function(){$l(this.g)},Qe.prototype.o=function(s){var a=this.g;if(typeof s=="string"){var c={};c.__data__=s,s=c}else this.v&&(c={},c.__data__=Cl(s),s=c);a.i.push(new ky(a.Ya++,s)),a.I==3&&xs(a)},Qe.prototype.N=function(){this.g.l=null,delete this.j,$l(this.g),delete this.g,Qe.Z.N.call(this)};function jh(s){Pl.call(this),s.__headers__&&(this.headers=s.__headers__,this.statusCode=s.__status__,delete s.__headers__,delete s.__status__);var a=s.__sm__;if(a){e:{for(const c in a){s=c;break e}s=void 0}(this.i=s)&&(s=this.i,a=a!==null&&s in a?a[s]:void 0),this.data=a}else this.data=s}S(jh,Pl);function Vh(){Al.call(this),this.status=1}S(Vh,Al);function pr(s){this.g=s}S(pr,Fh),pr.prototype.ra=function(){Ne(this.g,"a")},pr.prototype.qa=function(s){Ne(this.g,new jh(s))},pr.prototype.pa=function(s){Ne(this.g,new Vh)},pr.prototype.oa=function(){Ne(this.g,"b")},Qe.prototype.send=Qe.prototype.o,Qe.prototype.open=Qe.prototype.m,Qe.prototype.close=Qe.prototype.close,Nl.NO_ERROR=0,Nl.TIMEOUT=8,Nl.HTTP_ERROR=6,Ey.COMPLETE="complete",my.EventType=si,si.OPEN="a",si.CLOSE="b",si.ERROR="c",si.MESSAGE="d",Te.prototype.listen=Te.prototype.J,ce.prototype.listenOnce=ce.prototype.K,ce.prototype.getLastError=ce.prototype.Ha,ce.prototype.getLastErrorCode=ce.prototype.ya,ce.prototype.getStatus=ce.prototype.ca,ce.prototype.getResponseJson=ce.prototype.La,ce.prototype.getResponseText=ce.prototype.la,ce.prototype.send=ce.prototype.ea,ce.prototype.setWithCredentials=ce.prototype.Fa}).apply(typeof to<"u"?to:typeof self<"u"?self:typeof window<"u"?window:{});const Nd="@firebase/firestore",Od="4.9.2";/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Le{constructor(e){this.uid=e}isAuthenticated(){return this.uid!=null}toKey(){return this.isAuthenticated()?"uid:"+this.uid:"anonymous-user"}isEqual(e){return e.uid===this.uid}}Le.UNAUTHENTICATED=new Le(null),Le.GOOGLE_CREDENTIALS=new Le("google-credentials-uid"),Le.FIRST_PARTY=new Le("first-party-uid"),Le.MOCK_USER=new Le("mock-user");/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */let Cs="12.3.0";/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const qr=new Ac("@firebase/firestore");function ht(t,...e){if(qr.logLevel<=J.DEBUG){const n=e.map(zc);qr.debug(`Firestore (${Cs}): ${t}`,...n)}}function ey(t,...e){if(qr.logLevel<=J.ERROR){const n=e.map(zc);qr.error(`Firestore (${Cs}): ${t}`,...n)}}function zS(t,...e){if(qr.logLevel<=J.WARN){const n=e.map(zc);qr.warn(`Firestore (${Cs}): ${t}`,...n)}}function zc(t){if(typeof t=="string")return t;try{/**
* @license
* Copyright 2020 Google LLC
*
* Licensed under the Apache License, Version 2.0 (the "License");
* you may not use this file except in compliance with the License.
* You may obtain a copy of the License at
*
*   http://www.apache.org/licenses/LICENSE-2.0
*
* Unless required by applicable law or agreed to in writing, software
* distributed under the License is distributed on an "AS IS" BASIS,
* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
* See the License for the specific language governing permissions and
* limitations under the License.
*/return function(n){return JSON.stringify(n)}(t)}catch{return t}}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function gs(t,e,n){let r="Unexpected state";typeof e=="string"?r=e:n=e,ty(t,r,n)}function ty(t,e,n){let r=`FIRESTORE (${Cs}) INTERNAL ASSERTION FAILED: ${e} (ID: ${t.toString(16)})`;if(n!==void 0)try{r+=" CONTEXT: "+JSON.stringify(n)}catch{r+=" CONTEXT: "+n}throw ey(r),new Error(r)}function Gi(t,e,n,r){let i="Unexpected state";typeof n=="string"?i=n:r=n,t||ty(e,i,r)}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const G={CANCELLED:"cancelled",INVALID_ARGUMENT:"invalid-argument",FAILED_PRECONDITION:"failed-precondition"};class K extends Jt{constructor(e,n){super(e,n),this.code=e,this.message=n,this.toString=()=>`${this.name}: [code=${this.code}]: ${this.message}`}}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Ki{constructor(){this.promise=new Promise((e,n)=>{this.resolve=e,this.reject=n})}}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class ny{constructor(e,n){this.user=n,this.type="OAuth",this.headers=new Map,this.headers.set("Authorization",`Bearer ${e}`)}}class $S{getToken(){return Promise.resolve(null)}invalidateToken(){}start(e,n){e.enqueueRetryable(()=>n(Le.UNAUTHENTICATED))}shutdown(){}}class bS{constructor(e){this.token=e,this.changeListener=null}getToken(){return Promise.resolve(this.token)}invalidateToken(){}start(e,n){this.changeListener=n,e.enqueueRetryable(()=>n(this.token.user))}shutdown(){this.changeListener=null}}class BS{constructor(e){this.t=e,this.currentUser=Le.UNAUTHENTICATED,this.i=0,this.forceRefresh=!1,this.auth=null}start(e,n){Gi(this.o===void 0,42304);let r=this.i;const i=h=>this.i!==r?(r=this.i,n(h)):Promise.resolve();let o=new Ki;this.o=()=>{this.i++,this.currentUser=this.u(),o.resolve(),o=new Ki,e.enqueueRetryable(()=>i(this.currentUser))};const l=()=>{const h=o;e.enqueueRetryable(async()=>{await h.promise,await i(this.currentUser)})},u=h=>{ht("FirebaseAuthCredentialsProvider","Auth detected"),this.auth=h,this.o&&(this.auth.addAuthTokenListener(this.o),l())};this.t.onInit(h=>u(h)),setTimeout(()=>{if(!this.auth){const h=this.t.getImmediate({optional:!0});h?u(h):(ht("FirebaseAuthCredentialsProvider","Auth not yet detected"),o.resolve(),o=new Ki)}},0),l()}getToken(){const e=this.i,n=this.forceRefresh;return this.forceRefresh=!1,this.auth?this.auth.getToken(n).then(r=>this.i!==e?(ht("FirebaseAuthCredentialsProvider","getToken aborted due to token change."),this.getToken()):r?(Gi(typeof r.accessToken=="string",31837,{l:r}),new ny(r.accessToken,this.currentUser)):null):Promise.resolve(null)}invalidateToken(){this.forceRefresh=!0}shutdown(){this.auth&&this.o&&this.auth.removeAuthTokenListener(this.o),this.o=void 0}u(){const e=this.auth&&this.auth.getUid();return Gi(e===null||typeof e=="string",2055,{h:e}),new Le(e)}}class HS{constructor(e,n,r){this.P=e,this.T=n,this.I=r,this.type="FirstParty",this.user=Le.FIRST_PARTY,this.A=new Map}R(){return this.I?this.I():null}get headers(){this.A.set("X-Goog-AuthUser",this.P);const e=this.R();return e&&this.A.set("Authorization",e),this.T&&this.A.set("X-Goog-Iam-Authorization-Token",this.T),this.A}}class WS{constructor(e,n,r){this.P=e,this.T=n,this.I=r}getToken(){return Promise.resolve(new HS(this.P,this.T,this.I))}start(e,n){e.enqueueRetryable(()=>n(Le.FIRST_PARTY))}shutdown(){}invalidateToken(){}}class Dd{constructor(e){this.value=e,this.type="AppCheck",this.headers=new Map,e&&e.length>0&&this.headers.set("x-firebase-appcheck",this.value)}}class GS{constructor(e,n){this.V=n,this.forceRefresh=!1,this.appCheck=null,this.m=null,this.p=null,It(e)&&e.settings.appCheckToken&&(this.p=e.settings.appCheckToken)}start(e,n){Gi(this.o===void 0,3512);const r=o=>{o.error!=null&&ht("FirebaseAppCheckTokenProvider",`Error getting App Check token; using placeholder token instead. Error: ${o.error.message}`);const l=o.token!==this.m;return this.m=o.token,ht("FirebaseAppCheckTokenProvider",`Received ${l?"new":"existing"} token.`),l?n(o.token):Promise.resolve()};this.o=o=>{e.enqueueRetryable(()=>r(o))};const i=o=>{ht("FirebaseAppCheckTokenProvider","AppCheck detected"),this.appCheck=o,this.o&&this.appCheck.addTokenListener(this.o)};this.V.onInit(o=>i(o)),setTimeout(()=>{if(!this.appCheck){const o=this.V.getImmediate({optional:!0});o?i(o):ht("FirebaseAppCheckTokenProvider","AppCheck not yet detected")}},0)}getToken(){if(this.p)return Promise.resolve(new Dd(this.p));const e=this.forceRefresh;return this.forceRefresh=!1,this.appCheck?this.appCheck.getToken(e).then(n=>n?(Gi(typeof n.token=="string",44558,{tokenResult:n}),this.m=n.token,new Dd(n.token)):null):Promise.resolve(null)}invalidateToken(){this.forceRefresh=!0}shutdown(){this.appCheck&&this.o&&this.appCheck.removeTokenListener(this.o),this.o=void 0}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function KS(t){const e=typeof self<"u"&&(self.crypto||self.msCrypto),n=new Uint8Array(t);if(e&&typeof e.getRandomValues=="function")e.getRandomValues(n);else for(let r=0;r<t;r++)n[r]=Math.floor(256*Math.random());return n}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class qS{static newId(){const e="ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789",n=62*Math.floor(4.129032258064516);let r="";for(;r.length<20;){const i=KS(40);for(let o=0;o<i.length;++o)r.length<20&&i[o]<n&&(r+=e.charAt(i[o]%62))}return r}}function Rn(t,e){return t<e?-1:t>e?1:0}function XS(t,e){const n=Math.min(t.length,e.length);for(let r=0;r<n;r++){const i=t.charAt(r),o=e.charAt(r);if(i!==o)return Ta(i)===Ta(o)?Rn(i,o):Ta(i)?1:-1}return Rn(t.length,e.length)}const JS=55296,QS=57343;function Ta(t){const e=t.charCodeAt(0);return e>=JS&&e<=QS}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Ld="__name__";class wt{constructor(e,n,r){n===void 0?n=0:n>e.length&&gs(637,{offset:n,range:e.length}),r===void 0?r=e.length-n:r>e.length-n&&gs(1746,{length:r,range:e.length-n}),this.segments=e,this.offset=n,this.len=r}get length(){return this.len}isEqual(e){return wt.comparator(this,e)===0}child(e){const n=this.segments.slice(this.offset,this.limit());return e instanceof wt?e.forEach(r=>{n.push(r)}):n.push(e),this.construct(n)}limit(){return this.offset+this.length}popFirst(e){return e=e===void 0?1:e,this.construct(this.segments,this.offset+e,this.length-e)}popLast(){return this.construct(this.segments,this.offset,this.length-1)}firstSegment(){return this.segments[this.offset]}lastSegment(){return this.get(this.length-1)}get(e){return this.segments[this.offset+e]}isEmpty(){return this.length===0}isPrefixOf(e){if(e.length<this.length)return!1;for(let n=0;n<this.length;n++)if(this.get(n)!==e.get(n))return!1;return!0}isImmediateParentOf(e){if(this.length+1!==e.length)return!1;for(let n=0;n<this.length;n++)if(this.get(n)!==e.get(n))return!1;return!0}forEach(e){for(let n=this.offset,r=this.limit();n<r;n++)e(this.segments[n])}toArray(){return this.segments.slice(this.offset,this.limit())}static comparator(e,n){const r=Math.min(e.length,n.length);for(let i=0;i<r;i++){const o=wt.compareSegments(e.get(i),n.get(i));if(o!==0)return o}return Rn(e.length,n.length)}static compareSegments(e,n){const r=wt.isNumericId(e),i=wt.isNumericId(n);return r&&!i?-1:!r&&i?1:r&&i?wt.extractNumericId(e).compare(wt.extractNumericId(n)):XS(e,n)}static isNumericId(e){return e.startsWith("__id")&&e.endsWith("__")}static extractNumericId(e){return Vc.fromString(e.substring(4,e.length-2))}}class ut extends wt{construct(e,n,r){return new ut(e,n,r)}canonicalString(){return this.toArray().join("/")}toString(){return this.canonicalString()}toUriEncodedString(){return this.toArray().map(encodeURIComponent).join("/")}static fromString(...e){const n=[];for(const r of e){if(r.indexOf("//")>=0)throw new K(G.INVALID_ARGUMENT,`Invalid segment (${r}). Paths must not contain // in them.`);n.push(...r.split("/").filter(i=>i.length>0))}return new ut(n)}static emptyPath(){return new ut([])}}const YS=/^[_a-zA-Z][_a-zA-Z0-9]*$/;class Hn extends wt{construct(e,n,r){return new Hn(e,n,r)}static isValidIdentifier(e){return YS.test(e)}canonicalString(){return this.toArray().map(e=>(e=e.replace(/\\/g,"\\\\").replace(/`/g,"\\`"),Hn.isValidIdentifier(e)||(e="`"+e+"`"),e)).join(".")}toString(){return this.canonicalString()}isKeyField(){return this.length===1&&this.get(0)===Ld}static keyField(){return new Hn([Ld])}static fromServerFormat(e){const n=[];let r="",i=0;const o=()=>{if(r.length===0)throw new K(G.INVALID_ARGUMENT,`Invalid field path (${e}). Paths must not be empty, begin with '.', end with '.', or contain '..'`);n.push(r),r=""};let l=!1;for(;i<e.length;){const u=e[i];if(u==="\\"){if(i+1===e.length)throw new K(G.INVALID_ARGUMENT,"Path has trailing escape character: "+e);const h=e[i+1];if(h!=="\\"&&h!=="."&&h!=="`")throw new K(G.INVALID_ARGUMENT,"Path has invalid escape sequence: "+e);r+=h,i+=2}else u==="`"?(l=!l,i++):u!=="."||l?(r+=u,i++):(o(),i++)}if(o(),l)throw new K(G.INVALID_ARGUMENT,"Unterminated ` in path: "+e);return new Hn(n)}static emptyPath(){return new Hn([])}}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class qn{constructor(e){this.path=e}static fromPath(e){return new qn(ut.fromString(e))}static fromName(e){return new qn(ut.fromString(e).popFirst(5))}static empty(){return new qn(ut.emptyPath())}get collectionGroup(){return this.path.popLast().lastSegment()}hasCollectionId(e){return this.path.length>=2&&this.path.get(this.path.length-2)===e}getCollectionGroup(){return this.path.get(this.path.length-2)}getCollectionPath(){return this.path.popLast()}isEqual(e){return e!==null&&ut.comparator(this.path,e.path)===0}toString(){return this.path.toString()}static comparator(e,n){return ut.comparator(e.path,n.path)}static isDocumentKey(e){return e.length%2==0}static fromSegments(e){return new qn(new ut(e.slice()))}}function ZS(t,e,n,r){if(e===!0&&r===!0)throw new K(G.INVALID_ARGUMENT,`${t} and ${n} cannot be used together.`)}function eI(t){return typeof t=="object"&&t!==null&&(Object.getPrototypeOf(t)===Object.prototype||Object.getPrototypeOf(t)===null)}function tI(t){if(t===void 0)return"undefined";if(t===null)return"null";if(typeof t=="string")return t.length>20&&(t=`${t.substring(0,20)}...`),JSON.stringify(t);if(typeof t=="number"||typeof t=="boolean")return""+t;if(typeof t=="object"){if(t instanceof Array)return"an array";{const e=function(r){return r.constructor?r.constructor.name:null}(t);return e?`a custom ${e} object`:"an object"}}return typeof t=="function"?"a function":gs(12329,{type:typeof t})}function nI(t,e){if("_delegate"in t&&(t=t._delegate),!(t instanceof e)){if(e.name===t.constructor.name)throw new K(G.INVALID_ARGUMENT,"Type does not match the expected instance. Did you pass a reference from a different Firestore SDK?");{const n=tI(t);throw new K(G.INVALID_ARGUMENT,`Expected type '${e.name}', but it was: ${n}`)}}return t}/**
 * @license
 * Copyright 2025 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function de(t,e){const n={typeString:t};return e&&(n.value=e),n}function Ps(t,e){if(!eI(t))throw new K(G.INVALID_ARGUMENT,"JSON must be an object");let n;for(const r in e)if(e[r]){const i=e[r].typeString,o="value"in e[r]?{value:e[r].value}:void 0;if(!(r in t)){n=`JSON missing required field: '${r}'`;break}const l=t[r];if(i&&typeof l!==i){n=`JSON field '${r}' must be a ${i}.`;break}if(o!==void 0&&l!==o.value){n=`Expected '${r}' field to equal '${o.value}'`;break}}if(n)throw new K(G.INVALID_ARGUMENT,n);return!0}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const xd=-62135596800,Md=1e6;class Et{static now(){return Et.fromMillis(Date.now())}static fromDate(e){return Et.fromMillis(e.getTime())}static fromMillis(e){const n=Math.floor(e/1e3),r=Math.floor((e-1e3*n)*Md);return new Et(n,r)}constructor(e,n){if(this.seconds=e,this.nanoseconds=n,n<0)throw new K(G.INVALID_ARGUMENT,"Timestamp nanoseconds out of range: "+n);if(n>=1e9)throw new K(G.INVALID_ARGUMENT,"Timestamp nanoseconds out of range: "+n);if(e<xd)throw new K(G.INVALID_ARGUMENT,"Timestamp seconds out of range: "+e);if(e>=253402300800)throw new K(G.INVALID_ARGUMENT,"Timestamp seconds out of range: "+e)}toDate(){return new Date(this.toMillis())}toMillis(){return 1e3*this.seconds+this.nanoseconds/Md}_compareTo(e){return this.seconds===e.seconds?Rn(this.nanoseconds,e.nanoseconds):Rn(this.seconds,e.seconds)}isEqual(e){return e.seconds===this.seconds&&e.nanoseconds===this.nanoseconds}toString(){return"Timestamp(seconds="+this.seconds+", nanoseconds="+this.nanoseconds+")"}toJSON(){return{type:Et._jsonSchemaVersion,seconds:this.seconds,nanoseconds:this.nanoseconds}}static fromJSON(e){if(Ps(e,Et._jsonSchema))return new Et(e.seconds,e.nanoseconds)}valueOf(){const e=this.seconds-xd;return String(e).padStart(12,"0")+"."+String(this.nanoseconds).padStart(9,"0")}}Et._jsonSchemaVersion="firestore/timestamp/1.0",Et._jsonSchema={type:de("string",Et._jsonSchemaVersion),seconds:de("number"),nanoseconds:de("number")};function rI(t){return t.name==="IndexedDbTransactionError"}/**
 * @license
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class iI extends Error{constructor(){super(...arguments),this.name="Base64DecodeError"}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class lr{constructor(e){this.binaryString=e}static fromBase64String(e){const n=function(i){try{return atob(i)}catch(o){throw typeof DOMException<"u"&&o instanceof DOMException?new iI("Invalid base64 string: "+o):o}}(e);return new lr(n)}static fromUint8Array(e){const n=function(i){let o="";for(let l=0;l<i.length;++l)o+=String.fromCharCode(i[l]);return o}(e);return new lr(n)}[Symbol.iterator](){let e=0;return{next:()=>e<this.binaryString.length?{value:this.binaryString.charCodeAt(e++),done:!1}:{value:void 0,done:!0}}}toBase64(){return function(n){return btoa(n)}(this.binaryString)}toUint8Array(){return function(n){const r=new Uint8Array(n.length);for(let i=0;i<n.length;i++)r[i]=n.charCodeAt(i);return r}(this.binaryString)}approximateByteSize(){return 2*this.binaryString.length}compareTo(e){return Rn(this.binaryString,e.binaryString)}isEqual(e){return this.binaryString===e.binaryString}}lr.EMPTY_BYTE_STRING=new lr("");const Du="(default)";class Zo{constructor(e,n){this.projectId=e,this.database=n||Du}static empty(){return new Zo("","")}get isDefaultDatabase(){return this.database===Du}isEqual(e){return e instanceof Zo&&e.projectId===this.projectId&&e.database===this.database}}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class sI{constructor(e,n=null,r=[],i=[],o=null,l="F",u=null,h=null){this.path=e,this.collectionGroup=n,this.explicitOrderBy=r,this.filters=i,this.limit=o,this.limitType=l,this.startAt=u,this.endAt=h,this.Ie=null,this.Ee=null,this.de=null,this.startAt,this.endAt}}function oI(t){return new sI(t)}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */var Ud,W;(W=Ud||(Ud={}))[W.OK=0]="OK",W[W.CANCELLED=1]="CANCELLED",W[W.UNKNOWN=2]="UNKNOWN",W[W.INVALID_ARGUMENT=3]="INVALID_ARGUMENT",W[W.DEADLINE_EXCEEDED=4]="DEADLINE_EXCEEDED",W[W.NOT_FOUND=5]="NOT_FOUND",W[W.ALREADY_EXISTS=6]="ALREADY_EXISTS",W[W.PERMISSION_DENIED=7]="PERMISSION_DENIED",W[W.UNAUTHENTICATED=16]="UNAUTHENTICATED",W[W.RESOURCE_EXHAUSTED=8]="RESOURCE_EXHAUSTED",W[W.FAILED_PRECONDITION=9]="FAILED_PRECONDITION",W[W.ABORTED=10]="ABORTED",W[W.OUT_OF_RANGE=11]="OUT_OF_RANGE",W[W.UNIMPLEMENTED=12]="UNIMPLEMENTED",W[W.INTERNAL=13]="INTERNAL",W[W.UNAVAILABLE=14]="UNAVAILABLE",W[W.DATA_LOSS=15]="DATA_LOSS";/**
 * @license
 * Copyright 2022 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */new Vc([4294967295,4294967295],0);/**
 * @license
 * Copyright 2018 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const lI=41943040;/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const aI=1048576;function ka(){return typeof document<"u"?document:null}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class uI{constructor(e,n,r=1e3,i=1.5,o=6e4){this.Mi=e,this.timerId=n,this.d_=r,this.A_=i,this.R_=o,this.V_=0,this.m_=null,this.f_=Date.now(),this.reset()}reset(){this.V_=0}g_(){this.V_=this.R_}p_(e){this.cancel();const n=Math.floor(this.V_+this.y_()),r=Math.max(0,Date.now()-this.f_),i=Math.max(0,n-r);i>0&&ht("ExponentialBackoff",`Backing off for ${i} ms (base delay: ${this.V_} ms, delay with jitter: ${n} ms, last attempt: ${r} ms ago)`),this.m_=this.Mi.enqueueAfterDelay(this.timerId,i,()=>(this.f_=Date.now(),e())),this.V_*=this.A_,this.V_<this.d_&&(this.V_=this.d_),this.V_>this.R_&&(this.V_=this.R_)}w_(){this.m_!==null&&(this.m_.skipDelay(),this.m_=null)}cancel(){this.m_!==null&&(this.m_.cancel(),this.m_=null)}y_(){return(Math.random()-.5)*this.V_}}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class $c{constructor(e,n,r,i,o){this.asyncQueue=e,this.timerId=n,this.targetTimeMs=r,this.op=i,this.removalCallback=o,this.deferred=new Ki,this.then=this.deferred.promise.then.bind(this.deferred.promise),this.deferred.promise.catch(l=>{})}get promise(){return this.deferred.promise}static createAndSchedule(e,n,r,i,o){const l=Date.now()+r,u=new $c(e,n,l,i,o);return u.start(r),u}start(e){this.timerHandle=setTimeout(()=>this.handleDelayElapsed(),e)}skipDelay(){return this.handleDelayElapsed()}cancel(e){this.timerHandle!==null&&(this.clearTimeout(),this.deferred.reject(new K(G.CANCELLED,"Operation cancelled"+(e?": "+e:""))))}handleDelayElapsed(){this.asyncQueue.enqueueAndForget(()=>this.timerHandle!==null?(this.clearTimeout(),this.op().then(e=>this.deferred.resolve(e))):Promise.resolve())}clearTimeout(){this.timerHandle!==null&&(this.removalCallback(this),clearTimeout(this.timerHandle),this.timerHandle=null)}}var Fd,jd;(jd=Fd||(Fd={})).Ma="default",jd.Cache="cache";/**
 * @license
 * Copyright 2023 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */function cI(t){const e={};return t.timeoutSeconds!==void 0&&(e.timeoutSeconds=t.timeoutSeconds),e}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const Vd=new Map;/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const ry="firestore.googleapis.com",zd=!0;class $d{constructor(e){if(e.host===void 0){if(e.ssl!==void 0)throw new K(G.INVALID_ARGUMENT,"Can't provide ssl option if host option is not set");this.host=ry,this.ssl=zd}else this.host=e.host,this.ssl=e.ssl??zd;if(this.isUsingEmulator=e.emulatorOptions!==void 0,this.credentials=e.credentials,this.ignoreUndefinedProperties=!!e.ignoreUndefinedProperties,this.localCache=e.localCache,e.cacheSizeBytes===void 0)this.cacheSizeBytes=lI;else{if(e.cacheSizeBytes!==-1&&e.cacheSizeBytes<aI)throw new K(G.INVALID_ARGUMENT,"cacheSizeBytes must be at least 1048576");this.cacheSizeBytes=e.cacheSizeBytes}ZS("experimentalForceLongPolling",e.experimentalForceLongPolling,"experimentalAutoDetectLongPolling",e.experimentalAutoDetectLongPolling),this.experimentalForceLongPolling=!!e.experimentalForceLongPolling,this.experimentalForceLongPolling?this.experimentalAutoDetectLongPolling=!1:e.experimentalAutoDetectLongPolling===void 0?this.experimentalAutoDetectLongPolling=!0:this.experimentalAutoDetectLongPolling=!!e.experimentalAutoDetectLongPolling,this.experimentalLongPollingOptions=cI(e.experimentalLongPollingOptions??{}),function(r){if(r.timeoutSeconds!==void 0){if(isNaN(r.timeoutSeconds))throw new K(G.INVALID_ARGUMENT,`invalid long polling timeout: ${r.timeoutSeconds} (must not be NaN)`);if(r.timeoutSeconds<5)throw new K(G.INVALID_ARGUMENT,`invalid long polling timeout: ${r.timeoutSeconds} (minimum allowed value is 5)`);if(r.timeoutSeconds>30)throw new K(G.INVALID_ARGUMENT,`invalid long polling timeout: ${r.timeoutSeconds} (maximum allowed value is 30)`)}}(this.experimentalLongPollingOptions),this.useFetchStreams=!!e.useFetchStreams}isEqual(e){return this.host===e.host&&this.ssl===e.ssl&&this.credentials===e.credentials&&this.cacheSizeBytes===e.cacheSizeBytes&&this.experimentalForceLongPolling===e.experimentalForceLongPolling&&this.experimentalAutoDetectLongPolling===e.experimentalAutoDetectLongPolling&&function(r,i){return r.timeoutSeconds===i.timeoutSeconds}(this.experimentalLongPollingOptions,e.experimentalLongPollingOptions)&&this.ignoreUndefinedProperties===e.ignoreUndefinedProperties&&this.useFetchStreams===e.useFetchStreams}}class iy{constructor(e,n,r,i){this._authCredentials=e,this._appCheckCredentials=n,this._databaseId=r,this._app=i,this.type="firestore-lite",this._persistenceKey="(lite)",this._settings=new $d({}),this._settingsFrozen=!1,this._emulatorOptions={},this._terminateTask="notTerminated"}get app(){if(!this._app)throw new K(G.FAILED_PRECONDITION,"Firestore was not initialized using the Firebase SDK. 'app' is not available");return this._app}get _initialized(){return this._settingsFrozen}get _terminated(){return this._terminateTask!=="notTerminated"}_setSettings(e){if(this._settingsFrozen)throw new K(G.FAILED_PRECONDITION,"Firestore has already been started and its settings can no longer be changed. You can only modify settings before calling any other methods on a Firestore object.");this._settings=new $d(e),this._emulatorOptions=e.emulatorOptions||{},e.credentials!==void 0&&(this._authCredentials=function(r){if(!r)return new $S;switch(r.type){case"firstParty":return new WS(r.sessionIndex||"0",r.iamToken||null,r.authTokenFactory||null);case"provider":return r.client;default:throw new K(G.INVALID_ARGUMENT,"makeAuthCredentialsProvider failed due to invalid credential type")}}(e.credentials))}_getSettings(){return this._settings}_getEmulatorOptions(){return this._emulatorOptions}_freezeSettings(){return this._settingsFrozen=!0,this._settings}_delete(){return this._terminateTask==="notTerminated"&&(this._terminateTask=this._terminate()),this._terminateTask}async _restart(){this._terminateTask==="notTerminated"?await this._terminate():this._terminateTask="notTerminated"}toJSON(){return{app:this._app,databaseId:this._databaseId,settings:this._settings}}_terminate(){return function(n){const r=Vd.get(n);r&&(ht("ComponentProvider","Removing Datastore"),Vd.delete(n),r.terminate())}(this),Promise.resolve()}}function hI(t,e,n,r={}){var d;t=nI(t,iy);const i=Es(e),o=t._getSettings(),l={...o,emulatorOptions:t._getEmulatorOptions()},u=`${e}:${n}`;i&&(pm(`https://${u}`),gm("Firestore",!0)),o.host!==ry&&o.host!==u&&zS("Host has been set in both settings() and connectFirestoreEmulator(), emulator host will be used.");const h={...o,host:u,ssl:i,emulatorOptions:r};if(!sr(h,l)&&(t._setSettings(h),r.mockUserToken)){let k,S;if(typeof r.mockUserToken=="string")k=r.mockUserToken,S=Le.MOCK_USER;else{k=r1(r.mockUserToken,(d=t._app)==null?void 0:d.options.projectId);const E=r.mockUserToken.sub||r.mockUserToken.user_id;if(!E)throw new K(G.INVALID_ARGUMENT,"mockUserToken must contain 'sub' or 'user_id' field!");S=new Le(E)}t._authCredentials=new bS(new ny(k,S))}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class bc{constructor(e,n,r){this.converter=n,this._query=r,this.type="query",this.firestore=e}withConverter(e){return new bc(this.firestore,e,this._query)}}class Tt{constructor(e,n,r){this.converter=n,this._key=r,this.type="document",this.firestore=e}get _path(){return this._key.path}get id(){return this._key.path.lastSegment()}get path(){return this._key.path.canonicalString()}get parent(){return new Bc(this.firestore,this.converter,this._key.path.popLast())}withConverter(e){return new Tt(this.firestore,e,this._key)}toJSON(){return{type:Tt._jsonSchemaVersion,referencePath:this._key.toString()}}static fromJSON(e,n,r){if(Ps(n,Tt._jsonSchema))return new Tt(e,r||null,new qn(ut.fromString(n.referencePath)))}}Tt._jsonSchemaVersion="firestore/documentReference/1.0",Tt._jsonSchema={type:de("string",Tt._jsonSchemaVersion),referencePath:de("string")};class Bc extends bc{constructor(e,n,r){super(e,n,oI(r)),this._path=r,this.type="collection"}get id(){return this._query.path.lastSegment()}get path(){return this._query.path.canonicalString()}get parent(){const e=this._path.popLast();return e.isEmpty()?null:new Tt(this.firestore,null,new qn(e))}withConverter(e){return new Bc(this.firestore,e,this._path)}}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */const bd="AsyncQueue";class Bd{constructor(e=Promise.resolve()){this.Xu=[],this.ec=!1,this.tc=[],this.nc=null,this.rc=!1,this.sc=!1,this.oc=[],this.M_=new uI(this,"async_queue_retry"),this._c=()=>{const r=ka();r&&ht(bd,"Visibility state changed to "+r.visibilityState),this.M_.w_()},this.ac=e;const n=ka();n&&typeof n.addEventListener=="function"&&n.addEventListener("visibilitychange",this._c)}get isShuttingDown(){return this.ec}enqueueAndForget(e){this.enqueue(e)}enqueueAndForgetEvenWhileRestricted(e){this.uc(),this.cc(e)}enterRestrictedMode(e){if(!this.ec){this.ec=!0,this.sc=e||!1;const n=ka();n&&typeof n.removeEventListener=="function"&&n.removeEventListener("visibilitychange",this._c)}}enqueue(e){if(this.uc(),this.ec)return new Promise(()=>{});const n=new Ki;return this.cc(()=>this.ec&&this.sc?Promise.resolve():(e().then(n.resolve,n.reject),n.promise)).then(()=>n.promise)}enqueueRetryable(e){this.enqueueAndForget(()=>(this.Xu.push(e),this.lc()))}async lc(){if(this.Xu.length!==0){try{await this.Xu[0](),this.Xu.shift(),this.M_.reset()}catch(e){if(!rI(e))throw e;ht(bd,"Operation failed with retryable error: "+e)}this.Xu.length>0&&this.M_.p_(()=>this.lc())}}cc(e){const n=this.ac.then(()=>(this.rc=!0,e().catch(r=>{throw this.nc=r,this.rc=!1,ey("INTERNAL UNHANDLED ERROR: ",Hd(r)),r}).then(r=>(this.rc=!1,r))));return this.ac=n,n}enqueueAfterDelay(e,n,r){this.uc(),this.oc.indexOf(e)>-1&&(n=0);const i=$c.createAndSchedule(this,e,n,r,o=>this.hc(o));return this.tc.push(i),i}uc(){this.nc&&gs(47125,{Pc:Hd(this.nc)})}verifyOperationInProgress(){}async Tc(){let e;do e=this.ac,await e;while(e!==this.ac)}Ic(e){for(const n of this.tc)if(n.timerId===e)return!0;return!1}Ec(e){return this.Tc().then(()=>{this.tc.sort((n,r)=>n.targetTimeMs-r.targetTimeMs);for(const n of this.tc)if(n.skipDelay(),e!=="all"&&n.timerId===e)break;return this.Tc()})}dc(e){this.oc.push(e)}hc(e){const n=this.tc.indexOf(e);this.tc.splice(n,1)}}function Hd(t){let e=t.message||"";return t.stack&&(e=t.stack.includes(t.message)?t.stack:t.message+`
`+t.stack),e}class fI extends iy{constructor(e,n,r,i){super(e,n,r,i),this.type="firestore",this._queue=new Bd,this._persistenceKey=(i==null?void 0:i.name)||"[DEFAULT]"}async _terminate(){if(this._firestoreClient){const e=this._firestoreClient.terminate();this._queue=new Bd(e),this._firestoreClient=void 0,await e}}}function dI(t,e){const n=typeof t=="object"?t:_m(),r=typeof t=="string"?t:Du,i=Nc(n,"firestore").getImmediate({identifier:r});if(!i._initialized){const o=t1("firestore");o&&hI(i,...o)}return i}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Mt{constructor(e){this._byteString=e}static fromBase64String(e){try{return new Mt(lr.fromBase64String(e))}catch(n){throw new K(G.INVALID_ARGUMENT,"Failed to construct data from Base64 string: "+n)}}static fromUint8Array(e){return new Mt(lr.fromUint8Array(e))}toBase64(){return this._byteString.toBase64()}toUint8Array(){return this._byteString.toUint8Array()}toString(){return"Bytes(base64: "+this.toBase64()+")"}isEqual(e){return this._byteString.isEqual(e._byteString)}toJSON(){return{type:Mt._jsonSchemaVersion,bytes:this.toBase64()}}static fromJSON(e){if(Ps(e,Mt._jsonSchema))return Mt.fromBase64String(e.bytes)}}Mt._jsonSchemaVersion="firestore/bytes/1.0",Mt._jsonSchema={type:de("string",Mt._jsonSchemaVersion),bytes:de("string")};/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class sy{constructor(...e){for(let n=0;n<e.length;++n)if(e[n].length===0)throw new K(G.INVALID_ARGUMENT,"Invalid field name at argument $(i + 1). Field names must not be empty.");this._internalPath=new Hn(e)}isEqual(e){return this._internalPath.isEqual(e._internalPath)}}/**
 * @license
 * Copyright 2017 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Yn{constructor(e,n){if(!isFinite(e)||e<-90||e>90)throw new K(G.INVALID_ARGUMENT,"Latitude must be a number between -90 and 90, but was: "+e);if(!isFinite(n)||n<-180||n>180)throw new K(G.INVALID_ARGUMENT,"Longitude must be a number between -180 and 180, but was: "+n);this._lat=e,this._long=n}get latitude(){return this._lat}get longitude(){return this._long}isEqual(e){return this._lat===e._lat&&this._long===e._long}_compareTo(e){return Rn(this._lat,e._lat)||Rn(this._long,e._long)}toJSON(){return{latitude:this._lat,longitude:this._long,type:Yn._jsonSchemaVersion}}static fromJSON(e){if(Ps(e,Yn._jsonSchema))return new Yn(e.latitude,e.longitude)}}Yn._jsonSchemaVersion="firestore/geoPoint/1.0",Yn._jsonSchema={type:de("string",Yn._jsonSchemaVersion),latitude:de("number"),longitude:de("number")};/**
 * @license
 * Copyright 2024 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class Zn{constructor(e){this._values=(e||[]).map(n=>n)}toArray(){return this._values.map(e=>e)}isEqual(e){return function(r,i){if(r.length!==i.length)return!1;for(let o=0;o<r.length;++o)if(r[o]!==i[o])return!1;return!0}(this._values,e._values)}toJSON(){return{type:Zn._jsonSchemaVersion,vectorValues:this._values}}static fromJSON(e){if(Ps(e,Zn._jsonSchema)){if(Array.isArray(e.vectorValues)&&e.vectorValues.every(n=>typeof n=="number"))return new Zn(e.vectorValues);throw new K(G.INVALID_ARGUMENT,"Expected 'vectorValues' field to be a number array")}}}Zn._jsonSchemaVersion="firestore/vectorValue/1.0",Zn._jsonSchema={type:de("string",Zn._jsonSchemaVersion),vectorValues:de("object")};const pI=new RegExp("[~\\*/\\[\\]]");function gI(t,e,n){if(e.search(pI)>=0)throw Wd(`Invalid field path (${e}). Paths must not contain '~', '*', '/', '[', or ']'`,t);try{return new sy(...e.split("."))._internalPath}catch{throw Wd(`Invalid field path (${e}). Paths must not be empty, begin with '.', end with '.', or contain '..'`,t)}}function Wd(t,e,n,r,i){let o=`Function ${e}() called with invalid data`;o+=". ";let l="";return new K(G.INVALID_ARGUMENT,o+t+l)}/**
 * @license
 * Copyright 2020 Google LLC
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */class oy{constructor(e,n,r,i,o){this._firestore=e,this._userDataWriter=n,this._key=r,this._document=i,this._converter=o}get id(){return this._key.path.lastSegment()}get ref(){return new Tt(this._firestore,this._converter,this._key)}exists(){return this._document!==null}data(){if(this._document){if(this._converter){const e=new mI(this._firestore,this._userDataWriter,this._key,this._document,null);return this._converter.fromFirestore(e)}return this._userDataWriter.convertValue(this._document.data.value)}}get(e){if(this._document){const n=this._document.data.field(ly("DocumentSnapshot.get",e));if(n!==null)return this._userDataWriter.convertValue(n)}}}class mI extends oy{data(){return super.data()}}function ly(t,e){return typeof e=="string"?gI(t,e):e instanceof sy?e._internalPath:e._delegate._internalPath}class no{constructor(e,n){this.hasPendingWrites=e,this.fromCache=n}isEqual(e){return this.hasPendingWrites===e.hasPendingWrites&&this.fromCache===e.fromCache}}class jr extends oy{constructor(e,n,r,i,o,l){super(e,n,r,i,l),this._firestore=e,this._firestoreImpl=e,this.metadata=o}exists(){return super.exists()}data(e={}){if(this._document){if(this._converter){const n=new wo(this._firestore,this._userDataWriter,this._key,this._document,this.metadata,null);return this._converter.fromFirestore(n,e)}return this._userDataWriter.convertValue(this._document.data.value,e.serverTimestamps)}}get(e,n={}){if(this._document){const r=this._document.data.field(ly("DocumentSnapshot.get",e));if(r!==null)return this._userDataWriter.convertValue(r,n.serverTimestamps)}}toJSON(){if(this.metadata.hasPendingWrites)throw new K(G.FAILED_PRECONDITION,"DocumentSnapshot.toJSON() attempted to serialize a document with pending writes. Await waitForPendingWrites() before invoking toJSON().");const e=this._document,n={};return n.type=jr._jsonSchemaVersion,n.bundle="",n.bundleSource="DocumentSnapshot",n.bundleName=this._key.toString(),!e||!e.isValidDocument()||!e.isFoundDocument()?n:(this._userDataWriter.convertObjectMap(e.data.value.mapValue.fields,"previous"),n.bundle=(this._firestore,this.ref.path,"NOT SUPPORTED"),n)}}jr._jsonSchemaVersion="firestore/documentSnapshot/1.0",jr._jsonSchema={type:de("string",jr._jsonSchemaVersion),bundleSource:de("string","DocumentSnapshot"),bundleName:de("string"),bundle:de("string")};class wo extends jr{data(e={}){return super.data(e)}}class qi{constructor(e,n,r,i){this._firestore=e,this._userDataWriter=n,this._snapshot=i,this.metadata=new no(i.hasPendingWrites,i.fromCache),this.query=r}get docs(){const e=[];return this.forEach(n=>e.push(n)),e}get size(){return this._snapshot.docs.size}get empty(){return this.size===0}forEach(e,n){this._snapshot.docs.forEach(r=>{e.call(n,new wo(this._firestore,this._userDataWriter,r.key,r,new no(this._snapshot.mutatedKeys.has(r.key),this._snapshot.fromCache),this.query.converter))})}docChanges(e={}){const n=!!e.includeMetadataChanges;if(n&&this._snapshot.excludesMetadataChanges)throw new K(G.INVALID_ARGUMENT,"To include metadata changes with your document changes, you must also pass { includeMetadataChanges:true } to onSnapshot().");return this._cachedChanges&&this._cachedChangesIncludeMetadataChanges===n||(this._cachedChanges=function(i,o){if(i._snapshot.oldDocs.isEmpty()){let l=0;return i._snapshot.docChanges.map(u=>{const h=new wo(i._firestore,i._userDataWriter,u.doc.key,u.doc,new no(i._snapshot.mutatedKeys.has(u.doc.key),i._snapshot.fromCache),i.query.converter);return u.doc,{type:"added",doc:h,oldIndex:-1,newIndex:l++}})}{let l=i._snapshot.oldDocs;return i._snapshot.docChanges.filter(u=>o||u.type!==3).map(u=>{const h=new wo(i._firestore,i._userDataWriter,u.doc.key,u.doc,new no(i._snapshot.mutatedKeys.has(u.doc.key),i._snapshot.fromCache),i.query.converter);let d=-1,k=-1;return u.type!==0&&(d=l.indexOf(u.doc.key),l=l.delete(u.doc.key)),u.type!==1&&(l=l.add(u.doc),k=l.indexOf(u.doc.key)),{type:yI(u.type),doc:h,oldIndex:d,newIndex:k}})}}(this,n),this._cachedChangesIncludeMetadataChanges=n),this._cachedChanges}toJSON(){if(this.metadata.hasPendingWrites)throw new K(G.FAILED_PRECONDITION,"QuerySnapshot.toJSON() attempted to serialize a document with pending writes. Await waitForPendingWrites() before invoking toJSON().");const e={};e.type=qi._jsonSchemaVersion,e.bundleSource="QuerySnapshot",e.bundleName=qS.newId(),this._firestore._databaseId.database,this._firestore._databaseId.projectId;const n=[],r=[],i=[];return this.docs.forEach(o=>{o._document!==null&&(n.push(o._document),r.push(this._userDataWriter.convertObjectMap(o._document.data.value.mapValue.fields,"previous")),i.push(o.ref.path))}),e.bundle=(this._firestore,this.query._query,e.bundleName,"NOT SUPPORTED"),e}}function yI(t){switch(t){case 0:return"added";case 2:case 3:return"modified";case 1:return"removed";default:return gs(61501,{type:t})}}qi._jsonSchemaVersion="firestore/querySnapshot/1.0",qi._jsonSchema={type:de("string",qi._jsonSchemaVersion),bundleSource:de("string","QuerySnapshot"),bundleName:de("string"),bundle:de("string")};(function(e,n=!0){(function(i){Cs=i})(Zr),Gr(new or("firestore",(r,{instanceIdentifier:i,options:o})=>{const l=r.getProvider("app").getImmediate(),u=new fI(new BS(r.getProvider("auth-internal")),new GS(l,r.getProvider("app-check-internal")),function(d,k){if(!Object.prototype.hasOwnProperty.apply(d.options,["projectId"]))throw new K(G.INVALID_ARGUMENT,'"projectId" not provided in firebase.initializeApp.');return new Zo(d.options.projectId,k)}(l,i),l);return o={useFetchStreams:n,...o},u._setSettings(o),u},"PUBLIC").setMultipleInstances(!0)),Cn(Nd,Od,e),Cn(Nd,Od,"esm2020")})();const ay={apiKey:void 0,authDomain:void 0,projectId:void 0,storageBucket:void 0,messagingSenderId:void 0,appId:void 0},vI=Object.values(ay).every(t=>typeof t=="string"&&t.trim().length>0);let Ca=null,Gd=null,_I=null,Pa=null,Aa=null,wI=null,EI=null;if(vI)try{Ca=vm(ay),Gd=US(Ca),Gd.useDeviceLanguage(),_I=new xt,Pa=new Lt,Pa.addScope("public_profile"),Pa.addScope("email"),Aa=new Wi("apple.com"),Aa.addScope("email"),Aa.addScope("name"),wI=new ei,EI=dI(Ca)}catch{}X.lazy(()=>Be(()=>import("./ActivityLog-DYNPvfdA.js"),[]));X.lazy(()=>Be(()=>import("./ModelPerformance-CcYU0Q3B.js"),[]));X.lazy(()=>Be(()=>import("./ModelReasoning-BvrK2wil.js"),[]));X.lazy(()=>Be(()=>import("./LivePositions-DRRNUEpq.js"),[]));X.lazy(()=>Be(()=>import("./SystemStatus-vmTUPl10.js"),[]));X.lazy(()=>Be(()=>import("./PerformanceTrends-B47h9_Hu.js"),[]));X.lazy(()=>Be(()=>import("./MCPCouncil-DfNWhR_D.js"),[]));const SI=()=>Pe.jsxs("div",{className:"min-h-screen bg-brand-midnight text-brand-ice relative overflow-hidden flex items-center justify-center p-6",children:[Pe.jsx("div",{className:"pointer-events-none absolute inset-0 bg-sapphire-mesh opacity-60"}),Pe.jsx("div",{className:"pointer-events-none absolute inset-0 bg-sapphire-strata opacity-50"}),Pe.jsxs("div",{className:"relative max-w-3xl rounded-4xl border border-brand-border/70 bg-brand-abyss/80 p-10 text-center shadow-sapphire",children:[Pe.jsx("div",{className:"mx-auto mb-6 flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-accent-blue/20 text-3xl",children:"⏳"}),Pe.jsx("h1",{className:"text-3xl font-bold tracking-wide text-brand-ice",children:"Sapphire is calibrating for launch"}),Pe.jsxs("p",{className:"mt-4 text-brand-ice/80 leading-relaxed",children:["We're applying final production upgrades to the live trading stack and refreshing all community data. The dashboard will reopen by ",Pe.jsx("span",{className:"text-brand-accent-blue font-semibold",children:"10:30 PM Central Time"}),"with the full Sapphire experience."]}),Pe.jsxs("div",{className:"mt-8 space-y-2 text-sm text-brand-ice/60",children:[Pe.jsx("p",{children:"• Live traders remain on risk-managed standby during this upgrade window."}),Pe.jsx("p",{children:"• Telegram alerts will resume automatically once trading restarts."}),Pe.jsxs("p",{children:["• Follow updates on Twitter/X: ",Pe.jsx("span",{className:"text-brand-accent-blue",children:"@rari_sui"})]})]})]})]}),II=()=>{const[t,e]=X.useState("dashboard");return Pe.jsx(SI,{})};Ra.createRoot(document.getElementById("root")).render(Pe.jsx(rp.StrictMode,{children:Pe.jsx(II,{})}));export{rp as R,d0 as a,TI as b,$y as g,Pe as j,X as r};
