#include "mk64_interaction.h"
#include "dk64vr_input.h"
#include <cassert>
#include <cmath>
#include <cstdio>
using namespace mk64vr;
static bool near(float a,float b,float eps=.001f){return std::abs(a-b)<eps;}
int main(){
    FirstPersonConfig c;
    HandSample h[2]; for(auto& hand:h)hand.valid=true;
    h[0].pose.p={-c.radius,c.wheel.y,c.wheel.z}; h[1].pose.p={c.radius,c.wheel.y,c.wheel.z};
    FirstPersonControls controls;
    controls.update(h,true,false,true,false,c);
    h[0].grip=true; auto out=controls.update(h,true,false,true,false,c);
    assert(out.steering && out.wheelHands==1 && near(out.steer,0) && out.command==0);
    h[0].pose.p={-c.radius*.7071f,c.wheel.y+c.radius*.7071f,c.wheel.z};
    out=controls.update(h,true,false,true,false,c); assert(out.steer>.7f);
    h[1].grip=true; out=controls.update(h,true,false,true,false,c); assert(out.wheelHands==3 && out.steer>.7f);
    h[0].grip=false; out=controls.update(h,true,false,true,false,c); assert(out.steering && out.wheelHands==2);
    h[1].grip=false; out=controls.update(h,true,false,true,false,c); assert(!out.steering);
    // Independent sign oracle: lowering a freshly latched RIGHT rim hand is right steering.
    h[1].grip=true;controls.update(h,true,false,true,false,c);
    h[1].pose.p.y=c.wheel.y-c.radius*.5f;h[1].pose.p.x=c.radius*.8660254f;
    out=controls.update(h,true,false,true,false,c);assert(out.steer>.45f);
    out=controls.update(h,true,true,true,false,c);assert(!out.steering && !out.command);
    out=controls.update(h,true,false,true,false,c);assert(!out.steering && !out.command);
    h[1].grip=false;controls.update(h,true,false,true,false,c);
    // Fresh off-rim grip takes only the available single item, other hand can steer.
    h[1].pose.p={.4f,-.2f,-.2f}; h[1].grip=true;
    out=controls.update(h,true,false,true,false,c); assert(out.command==1 && out.itemHand==1);
    h[0].pose.p={-c.radius,c.wheel.y,c.wheel.z}; h[0].grip=true;
    out=controls.update(h,true,false,false,true,c); assert(out.steering && out.itemHand==1);
    h[1].velocity={0,0,-2};h[1].velocityValid=true;h[1].grip=false;
    out=controls.update(h,true,false,false,true,c); assert(out.command==2 && !out.rear && near(out.velocity.z,-2) && out.itemHand==1);
    // Invalid tracking behind shoulder never releases. Resume-held and first release
    // stay disarmed; a fresh press and release is required for retained native item.
    controls=FirstPersonControls{}; h[0].grip=false;h[1].grip=false;
    controls.update(h,true,false,true,false,c);h[1].grip=true;controls.update(h,true,false,true,false,c);
    h[1].pose.p.z=.3f;h[1].valid=false;h[1].grip=false;
    out=controls.update(h,true,false,false,true,c);assert(out.command==0);
    h[1].valid=true;h[1].grip=true;controls.update(h,true,false,false,true,c);
    h[1].grip=false;out=controls.update(h,true,false,false,true,c);assert(out.command==0);
    h[1].grip=true;controls.update(h,true,false,false,true,c);
    h[1].grip=false;out=controls.update(h,true,false,false,true,c);assert(out.command==2 && out.rear);
    for(int reason=0;reason<3;reason++) {
        controls=FirstPersonControls{}; h[1].grip=false;h[1].pose.p.z=-.2f;
        controls.update(h,true,false,true,false,c);h[1].grip=true;controls.update(h,true,false,true,false,c);
        out=controls.update(h,reason!=0,reason!=0,false,true,c);assert(!out.command);
        h[1].grip=false;out=controls.update(h,true,false,false,true,c);assert(!out.command);
        h[1].grip=true;controls.update(h,true,false,false,true,c);h[1].velocity={.1f,0,0};h[1].grip=false;
        out=controls.update(h,true,false,false,true,c);assert(out.command==2 && near(out.velocity.x,0));
    }
    // Native View routing: a tap toggles only in gameplay; hold recentres without tap.
    dk64vr::InputMapper mapper; dk64vr::InputSample s; s.valid=true;
    dk64vr::InputContext context;context.viewTogglesCamera=true;
    dk64vr::InputConfig config; mapper.update(s,config,context,0,.01f);
    s.view=true;mapper.update(s,config,context,.1,.01f);s.view=false;
    auto r=mapper.update(s,config,context,.3,.01f);assert(r.toggleCamera && !(r.navHeld&dk64vr::nav::ToggleMenu));
    s.view=true;mapper.update(s,config,context,.5,.01f);
    r=mapper.update(s,config,context,1.6,.01f);assert(r.recentre && !r.toggleCamera);
    s.view=false;r=mapper.update(s,config,context,1.8,.01f);assert(!r.toggleCamera);
    context.menuOpen=true;s.view=true;mapper.update(s,config,context,2,.01f);s.view=false;
    r=mapper.update(s,config,context,2.2,.01f);assert(!r.toggleCamera && (r.navHeld&dk64vr::nav::ToggleMenu));
    // The same reset used by camera toggle and View hold disarms BOTH the wheel and
    // retained-item grip; releasing View/physical grips cannot queue a throw or steer.
    controls=FirstPersonControls{};h[0].grip=h[1].grip=false;
    h[0].pose.p={-c.radius,c.wheel.y,c.wheel.z};h[1].pose.p={.4f,-.2f,-.2f};
    controls.update(h,true,false,true,false,c);h[0].grip=h[1].grip=true;
    out=controls.update(h,true,false,true,false,c);assert(out.command==1 && out.steering);
    out=controls.update(h,true,true,false,true,c);assert(!out.command && !out.steering && out.itemHand==1);
    out=controls.update(h,true,false,false,true,c);assert(!out.command && !out.steering);
    h[0].grip=h[1].grip=false;out=controls.update(h,true,false,false,true,c);assert(!out.command && !out.steering);
    // All authored rigs deform their original source vertices via actual production skin matrices.
    for(int racer=0;racer<8;racer++)for(int hand=0;hand<2;hand++) {
        Pose wrist{{},{hand?.20f:-.20f,-.20f,-.20f}};
        auto a=armSkinMatrix(racer,hand,1,31,wrist,.005f,mk64_arm_rigs[racer].eye_height);
        wrist.q=quatFromYaw(.8f);auto b=armSkinMatrix(racer,hand,1,31,wrist,.005f,mk64_arm_rigs[racer].eye_height);
        assert(!near(a.m[0][0],b.m[0][0],1e-5f));
        for(auto& row:b.m)for(float value:row)assert(std::isfinite(value));
        if(racer==3){ auto shoulder=armSkinMatrix(racer,hand,0,0,wrist,.005f,5.48f);auto distal=armSkinMatrix(racer,hand,0,31,wrist,.005f,5.48f);assert(!near(shoulder.m[3][2],distal.m[3][2])); }
    }
    // Eye, local kart, wheel and shoulders share the same rigid basis even when
    // source interpolation differs from the low-smoothed seat at large coordinates.
    for(int tick=0;tick<20;tick++) {
        const float heading=tick*.15f;
        Mat4 source=poseMatrix({quatFromYaw(heading),{10000.f+tick*5,2,-20000.f+tick*3}});
        Pose smoothedSeat=seatPose({9995.f+tick*5,2,-20003.f+tick*3},heading+3.14159265f,6,0);
        Mat4 view=rigidInverse(poseMatrix(smoothedSeat));
        Mat4 correction=kartRegistration(source,view,6,0);
        Vec3 kartOrigin=transformPoint({},mul(mul(source,correction),view));
        assert(near(kartOrigin.x,0,.01f) && near(kartOrigin.y,-6,.01f) && near(kartOrigin.z,0,.01f));
        Vec3 kartFront=transformDir({0,0,1},mul(mul(source,correction),view));
        assert(near(kartFront.x,0,.001f) && near(kartFront.z,-1,.001f));
    }
    for(int p=0;p<dk64vr::profileCount();p++) {
        const auto& profile=dk64vr::profileAt(p);bool grip[2]{};
        for(int i=0;i<profile.count;i++){grip[0]|=profile.bindings[i].action==dk64vr::ActGripLeft;grip[1]|=profile.bindings[i].action==dk64vr::ActGripRight;}
        assert(grip[0]&&grip[1]);
    }
    puts("first person production controls, View routing, all-eight rig skin transforms passed");
}
