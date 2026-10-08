#include "mk64_interaction.h"
#include <algorithm>
#include <cmath>
namespace mk64vr {
static Vec3 sub(Vec3 a, Vec3 b) { return {a.x-b.x,a.y-b.y,a.z-b.z}; }
static Vec3 add(Vec3 a, Vec3 b) { return {a.x+b.x,a.y+b.y,a.z+b.z}; }
static Vec3 scale(Vec3 a, float s) { return {a.x*s,a.y*s,a.z*s}; }
static float length(Vec3 a) { return float(std::hypot(double(a.x),double(a.y),double(a.z))); }
FirstPersonOutput FirstPersonControls::update(const HandSample hands[2], bool active, bool reset,
    bool available, bool held, const FirstPersonConfig& c) {
    FirstPersonOutput out;
    int releaseHand=-1;
    if (!held && !available) holder = -1;
    for (int h=0; h<2; ++h) {
        const auto& hand=hands[h];
        if (!active || reset || !hand.valid) {
            armed[h]=false; previous[h]=hand.grip; wheel[h]=false;
            continue;
        }
        const bool wasArmed=armed[h];
        if (!hand.grip) armed[h]=true;
        const Vec3 d=sub(hand.pose.p,c.wheel);
        const float angle=float(std::atan2(double(d.y),double(d.x)));
        const bool rim=std::abs(length({d.x,d.y,0})-c.radius)<=c.rimTolerance && std::abs(d.z)<=c.rimTolerance;
        if (hand.grip && !previous[h] && armed[h]) {
            if (holder==h && held) { /* rearm retained item after safety reset */ }
            else if (rim && holder!=h) {
                wheel[h]=true; latchAngle[h]=angle; latchWheel[h]=wheelAngle;
            } else if (holder<0 && available && !held) {
                holder=h; out.command=1; available=false;
            } else if (held && holder<0) holder=h;
        }
        if (!hand.grip && previous[h] && wasArmed && holder==h && held) {
            out.command=2; releaseHand=h; out.rear=hand.pose.p.z>c.shoulderZ;
            if (hand.velocityValid && length(hand.velocity)>c.quietSpeed) out.velocity=hand.velocity;
            holder=-1;
        }
        if (!hand.grip) wheel[h]=false;
        previous[h]=hand.grip;
    }
    float angleSum=0; int count=0;
    for (int h=0; h<2; ++h) if(wheel[h]) {
        const Vec3 d=sub(hands[h].pose.p,c.wheel);
        const float a=float(std::atan2(double(d.y),double(d.x)));
        // Clockwise viewed from the seat steers right.
        angleSum+=latchWheel[h]-wrapAngle(a-latchAngle[h]); ++count; out.wheelHands|=1<<h;
    }
    if(count) wheelAngle=std::clamp(angleSum/count,-c.maxTurn,c.maxTurn);
    else wheelAngle=0;
    out.angle=wheelAngle; out.steering=count>0; out.steer=wheelAngle/c.maxTurn; out.itemHand=releaseHand>=0?releaseHand:holder;
    return out;
}
void HeldItemAttachment::update(bool held, int hand, bool tracked, Vec3 position, Quat orientation) {
    if(!held) { valid=false; return; }
    const float norm=orientation.x*orientation.x+orientation.y*orientation.y+orientation.z*orientation.z+orientation.w*orientation.w;
    if(hand>=0 && hand<2 && tracked && std::isfinite(norm) && norm>.00001f &&
        std::isfinite(position.x) && std::isfinite(position.y) && std::isfinite(position.z)) {
        local=position; rotation=quatNormalize(orientation); valid=true;
    }
}
bool HeldItemAttachment::transform(Mat4& model, const Mat4& seatView, bool orient, Vec3 grip, int actorType, float worldScale) const {
    if(!valid)return false;
    const float hand[3]={local.x,local.y,local.z}, q[4]={rotation.x,rotation.y,rotation.z,rotation.w};
    float target[3];mk64_vr_held_item_anchor(target,hand,q,actorType,worldScale);
    const Vec3 anchor{target[0],target[1],target[2]};
    if(orient) {
        // The native draw supplies visual scale. Only the held prop receives the
        // trusted grip orientation; loss retains it in the moving seat basis.
        const float size=length({model.m[0][0],model.m[0][1],model.m[0][2]});
        Mat4 posed=poseMatrix({rotation,sub(anchor,quatRotate(rotation,scale(grip,size)))});
        for(int r=0;r<3;r++)for(int c=0;c<3;c++)posed.m[r][c]*=size;
        model=mul(posed,rigidInverse(seatView)); return true;
    }
    const Vec3 world=transformPoint(anchor,rigidInverse(seatView));
    model.m[3][0]=world.x;model.m[3][1]=world.y;model.m[3][2]=world.z;
    return true;
}
Pose seatPose(Vec3 p, float heading, float height, float forward) {
    Pose seat{quatFromYaw(heading),p};
    seat.p=add(p,quatRotate(seat.q,{0,height,-forward})); return seat;
}
ArmSolution solveArm(Vec3 shoulder, Vec3 wrist, float upperLength, float lowerLength, Vec3 pole, Quat wristRotation) {
    ArmSolution out;
    Vec3 delta=sub(wrist,shoulder); float distance=length(delta);
    Vec3 axis=distance>.0001f?scale(delta,1/distance):Vec3{0,0,-1};
    // Cartoon source limbs are shorter than a seated human reach. Extend only
    // their bone axes, bounded for extreme controller poses; preserve mesh width.
    const float extension=std::clamp(distance/std::max(.001f,upperLength+lowerLength-.001f),1.f,2.5f);
    upperLength*=extension; lowerLength*=extension;
    const float reach=std::clamp(distance,std::abs(upperLength-lowerLength)+.001f,upperLength+lowerLength-.001f);
    out.wrist=add(shoulder,scale(axis,reach));
    Vec3 bend=sub(pole,scale(axis,dot(pole,axis)));
    if(length(bend)<.001f) bend=cross(axis,{0,1,0});
    if(length(bend)<.001f) bend=cross(axis,{1,0,0});
    bend=normalize(bend);
    const float along=(upperLength*upperLength-lowerLength*lowerLength+reach*reach)/(2*reach);
    out.elbow=add(shoulder,add(scale(axis,along),scale(bend,float(std::sqrt(double(std::max(0.f,upperLength*upperLength-along*along)))))));
    const Vec3 z=normalize(sub(out.elbow,shoulder)), x=normalize(cross(bend,z)), y=cross(z,x);
    out.upper=poseMatrix({quatFromBasis(x,y,z),shoulder});
    // Forearm mesh includes the hand: retain the tracked wrist roll/orientation.
    out.lower=poseMatrix({quatNormalize(wristRotation),out.elbow});
    return out;
}
static Quat fromTo(Vec3 from, Vec3 to) {
    from=normalize(from); to=normalize(to); const float d=dot(from,to);
    if(d<-.9999f) { Vec3 axis=normalize(cross(from,{0,1,0})); if(length(axis)<.1f) axis={1,0,0}; return {axis.x,axis.y,axis.z,0}; }
    Vec3 axis=cross(from,to); return quatNormalize({axis.x,axis.y,axis.z,1+d});
}
static Mat4 around(Quat rotation, Vec3 sourcePivot, Vec3 targetPivot, float scaleFactor) {
    Mat4 m=poseMatrix({rotation,{}},1);
    for(int r=0;r<3;r++) for(int c=0;c<3;c++) m.m[r][c]*=scaleFactor;
    const Vec3 p=transformDir(sourcePivot,m);
    m.m[3][0]=targetPivot.x-p.x; m.m[3][1]=targetPivot.y-p.y; m.m[3][2]=targetPivot.z-p.z;
    return m;
}
static Mat4 aroundBone(Quat rotation, Vec3 sourcePivot, Vec3 targetPivot, float modelScale,
                       Vec3 sourceBone, float targetLength) {
    const Vec3 n=normalize(sourceBone);
    const float ratio=targetLength/std::max(.0001f,length(sourceBone)*modelScale);
    const float axis[3]={n.x,n.y,n.z};
    Mat4 strain;
    for(int r=0;r<3;r++)for(int c=0;c<3;c++)strain.m[r][c]+=(ratio-1)*axis[r]*axis[c];
    Mat4 result=mul(strain,around(rotation,{}, {},modelScale));
    const Vec3 p=transformDir(sourcePivot,result);
    result.m[3][0]=targetPivot.x-p.x;result.m[3][1]=targetPivot.y-p.y;result.m[3][2]=targetPivot.z-p.z;
    return result;
}
Mat4 armSkinMatrix(int character, int hand, int lower, int weight, const Pose& wrist, float modelScale, float eyeHeight) {
    const float values[]={wrist.p.x,wrist.p.y,wrist.p.z,wrist.q.x,wrist.q.y,wrist.q.z,wrist.q.w,modelScale,eyeHeight};
    bool finite=character>=0 && character<8 && hand>=0 && hand<2 && modelScale>.00001f && modelScale<1;
    for(float v:values)finite=finite && std::isfinite(v);
    if(!finite) {
        Mat4 hidden;hidden.m[0][0]=hidden.m[1][1]=hidden.m[2][2]=.00001f;hidden.m[3][2]=1;return hidden;
    }
    const auto& rig=mk64_arm_rigs[character]; const float side=hand==0?1.f:-1.f;
    // Amped model +X is left and +Z forward, opposite the seat X/Z axes.
    Vec3 sourceShoulder{rig.shoulder[0]*side,rig.shoulder[1],rig.shoulder[2]};
    Vec3 sourceElbow{rig.elbow[0]*side,rig.elbow[1],rig.elbow[2]};
    Vec3 sourceWrist{rig.wrist[0]*side,rig.wrist[1],rig.wrist[2]};
    auto toSeat=[&](Vec3 a){return Vec3{-a.x*modelScale,a.y*modelScale,-a.z*modelScale};};
    Vec3 shoulder=toSeat(add({rig.base[0],rig.base[1],rig.base[2]},sourceShoulder)); shoulder.y-=eyeHeight;
    const float upperLength=length(sourceElbow)*modelScale, lowerLength=length(sourceWrist)*modelScale;
    // The controller/item point is the authored hand's grasp contact, not its palm
    // centre. Move only the skin's palm behind that contact in tracked hand axes.
    const Vec3 palmTarget=add(wrist.p,quatRotate(wrist.q,{0,0,rig.grip_forward*modelScale}));
    auto solved=solveArm(shoulder,palmTarget,upperLength,lowerLength,{hand?1.f:-1.f,-.5f,.4f},wrist.q);
    const Quat rest=quatFromYaw(3.141592653589793f);
    const Quat upperQ=quatMul(fromTo(toSeat(sourceElbow),sub(solved.elbow,shoulder)),rest);
    const Quat lowerQ=quatMul(fromTo(toSeat(sourceWrist),sub(solved.wrist,solved.elbow)),rest);
    // Grip-pose basis is also camera right/up/back. Rest model basis faces +Z.
    const Quat handQ=quatMul(wrist.q,rest);
    Mat4 upper=aroundBone(upperQ,{},shoulder,modelScale,sourceElbow,length(sub(solved.elbow,shoulder)));
    Mat4 fore=aroundBone(lowerQ,lower?Vec3{}:sourceElbow,solved.elbow,modelScale,sourceWrist,length(sub(solved.wrist,solved.elbow)));
    Mat4 distal=around(handQ,lower?sourceWrist:add(sourceElbow,sourceWrist),solved.wrist,modelScale);
    float t=weight/31.f; Mat4 a=fore,b=distal;
    if(!lower && character!=3) return upper;
    if(!lower) { if(t<.5f) {a=upper;b=fore;t*=2;} else t=(t-.5f)*2; }
    Mat4 out; for(int r=0;r<4;r++)for(int c=0;c<4;c++) out.m[r][c]=a.m[r][c]*(1-t)+b.m[r][c]*t;
    return out;
}

Mat4 kartRegistration(const Mat4& source,const Mat4& seatView,float eyeHeight,float forward) {
    // Remove only native yaw/translation; retain authored tilt, animation and scale.
    const float yaw=float(std::atan2(double(source.m[2][0]),double(source.m[2][2])));
    Mat4 basis=poseMatrix({quatFromYaw(yaw),{source.m[3][0],source.m[3][1],source.m[3][2]}});
    Mat4 target=poseMatrix({quatFromYaw(3.141592653589793f),{0,-eyeHeight,forward}});
    return mul(rigidInverse(basis),mul(target,rigidInverse(seatView)));
}

}
