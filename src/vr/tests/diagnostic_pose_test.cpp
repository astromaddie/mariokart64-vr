#include "../diag/mk64_diag_pose.h"
#include <cstdio>
#include <cstdlib>
#include <initializer_list>

using namespace dk64vr;
using namespace mk64vrdiag;
static unsigned checks;
static void require(bool value) { ++checks; if (!value) { std::fprintf(stderr, "diagnostic pose check %u failed\n", checks); std::exit(1); } }
static bool near(float a, float b) { return std::fabs(a-b) < 0.00001f; }
static void samePose(const Pose& a, const Pose& b) {
    require(near(a.p.x,b.p.x) && near(a.p.y,b.p.y) && near(a.p.z,b.p.z));
    require(near(a.q.x,b.q.x) && near(a.q.y,b.q.y) && near(a.q.z,b.q.z) && near(a.q.w,b.q.w));
}

int main() {
    const char* invalidSeconds[] = {nullptr, "", "0", "-1", "121", "90x", "90.5", " 90", "999999999999999999999999"};
    for (const char* seconds : invalidSeconds)
        require(!parseHeadOffset(seconds,"1",nullptr,nullptr).enabled);
    for (const char* value : {"", "nan", "inf", "-inf", "20.1", "-20.1", "1x", "1 2", " 1", "1e999"}) {
        require(!parseHeadOffset("90",value,nullptr,nullptr).enabled);
        require(!parseHeadOffset("90","1",value,nullptr).enabled);
        require(!parseHeadOffset("90","1","2",value).enabled);
    }
    require(!parseHeadOffset("90",nullptr,nullptr,nullptr).enabled);
    const auto offset = parseHeadOffset("90","2.5","-1","-20");
    require(offset.enabled && offset.lastGameFrame==2700);
    require(parseHeadOffset("120","20",nullptr,nullptr).enabled);
    Pose head;
    head.p = {0.4f,1.2f,-0.3f};
    head.q = quatNormalize({0.1f,0.5f,0.15f,0.8f});
    samePose(offsetHead(head,offset,false,true,900),head);
    samePose(offsetHead(head,offset,true,false,900),head);
    samePose(offsetHead(head,offset,true,true,0),head);
    samePose(offsetHead(head,offset,true,true,2701),head);
    samePose(offsetHead(head,{},true,true,900),head);
    const Pose moved = offsetHead(head,offset,true,true,2700);
    require(near(moved.p.x,head.p.x+2.5f) && near(moved.p.y,head.p.y-1) && near(moved.p.z,head.p.z-20));
    Pose rotationOnly = moved; rotationOnly.p = head.p; samePose(rotationOnly,head);
    Pose left, right; left.p.x=-0.032f; right.p.x=0.032f;
    const Pose eyes[] = {poseMul(moved,left),poseMul(moved,right)};
    const Vec3 separation = {eyes[1].p.x-eyes[0].p.x,eyes[1].p.y-eyes[0].p.y,eyes[1].p.z-eyes[0].p.z};
    require(near(std::sqrt(dot(separation,separation)),0.064f));
    require(near((eyes[0].p.x+eyes[1].p.x)*0.5f,moved.p.x));
    require(near((eyes[0].p.y+eyes[1].p.y)*0.5f,moved.p.y));
    require(near((eyes[0].p.z+eyes[1].p.z)*0.5f,moved.p.z));
    for (const Pose eye : {left,right}) {
        const Pose before = poseMul(head,eye), after = poseMul(moved,eye);
        require(near(after.p.x-before.p.x,2.5f) && near(after.p.y-before.p.y,-1) && near(after.p.z-before.p.z,-20));
    }
    std::printf("PASS %u diagnostic pose checks\n",checks);
}
